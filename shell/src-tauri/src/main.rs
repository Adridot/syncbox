// Syncbox shell supervisor. Order is load-bearing (POC #2 / SPEC-UNIFIED 6.6):
// single-instance registered FIRST (second launch self-exits, callback never
// re-spawns); sidecar spawned in its OWN process group (pgid == pid, killpg
// safe); child output always consumed; crash vs intent decided by a flag set
// BEFORE any kill (exit codes cannot discriminate - POC #2 T6); bounded
// restart 3x backoff 1/2/4 s then a `backend-down` event to the UI; manual
// `restart_sidecar` command after exhaustion; shutdown handshake on exit =
// POST /shutdown -> bounded wait -> SIGTERM group -> SIGKILL group.
//
// macOS-only code paths for v1; Windows is deferred.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Emitter, Manager};

const SIDECAR_ADDR: (&str, u16) = ("127.0.0.1", 8766);
const MAX_RESTARTS: u32 = 3;
const BACKOFF_SECS: [u64; 3] = [1, 2, 4];

/// Set BEFORE killing: distinguishes intentional shutdown from a crash.
static INTENT_SHUTDOWN: AtomicBool = AtomicBool::new(false);
/// One supervisor thread at a time (restart command vs initial setup).
static SUPERVISING: AtomicBool = AtomicBool::new(false);

struct Sidecar(Mutex<Option<Child>>);

fn sidecar_command(app: &tauri::AppHandle) -> Command {
    let mut cmd = if cfg!(debug_assertions) {
        // Dev seam: the repo venv, exactly the M4 recipe (pytest-style
        // PYTHONPATH import; no build backend in the venv by design).
        let repo_root = concat!(env!("CARGO_MANIFEST_DIR"), "/../..");
        let mut cmd = Command::new(format!("{repo_root}/sidecar/.venv/bin/python"));
        cmd.args(["-u", "-m", "syncbox"])
            .current_dir(format!("{repo_root}/sidecar"))
            .env("PYTHONPATH", format!("{repo_root}/sidecar/src"));
        cmd
    } else {
        // Release: the PyInstaller onedir bundled under Resources/sidecar
        // (6.11). The whole onedir ships as a bundle resource - exe and its
        // _internal/ must stay adjacent, which externalBin (one file per
        // target triple) cannot carry alone.
        let bin = app
            .path()
            .resource_dir()
            .expect("app bundle has a resource dir")
            .join("sidecar/syncbox-sidecar");
        Command::new(bin)
    };
    cmd.stdout(Stdio::piped())
        .stderr(Stdio::piped())
        // Own process group at spawn: killpg is only safe when pgid == pid.
        // Inheriting the parent's pgid means killpg kills the shell itself
        // (POC #2 learned this live).
        .process_group(0);
    cmd
}

fn spawn_sidecar(app: &tauri::AppHandle) -> std::io::Result<Child> {
    let mut child = sidecar_command(app).spawn()?;
    // 6.6: ALWAYS consume child output (an unread pipe eventually blocks and
    // crashes the sidecar). Forward to the shell's stderr for dev visibility.
    for (name, stream) in [
        ("out", child.stdout.take().map(|s| Box::new(s) as Box<dyn Read + Send>)),
        ("err", child.stderr.take().map(|s| Box::new(s) as Box<dyn Read + Send>)),
    ] {
        if let Some(stream) = stream {
            std::thread::spawn(move || {
                eprintln!("SIDECAR_{name}_DRAIN_STARTED");
                let mut stream = stream;
                let mut buffer = [0u8; 8192];
                loop {
                    let count = match stream.read(&mut buffer) {
                        Ok(0) | Err(_) => break,
                        Ok(count) => count,
                    };
                    // Lock stderr only for this chunk. Holding the global
                    // lock while waiting for sidecar output would block the
                    // supervisor's own lifecycle markers indefinitely.
                    let mut stderr = std::io::stderr().lock();
                    if stderr.write_all(&buffer[..count]).is_err() {
                        break;
                    }
                    let _ = stderr.flush();
                }
            });
        }
    }
    eprintln!("SIDECAR_SPAWNED pid={}", child.id());
    Ok(child)
}

/// Supervisor loop (6.6): spawn, watch for exit, restart with bounded
/// backoff on crash, emit `backend-down` on exhaustion. Returns silently
/// when the shutdown path takes ownership of the child.
fn start_supervisor(app: tauri::AppHandle) -> bool {
    if SUPERVISING.swap(true, Ordering::SeqCst) {
        return false; // already supervising
    }
    std::thread::spawn(move || {
        // Three crashes over this supervisor's lifetime require a manual
        // restart, which creates a fresh supervisor and strike counter.
        let mut attempts: u32 = 0;
        loop {
            let state = app.state::<Sidecar>();
            let spawned = {
                // Serialize intent-check, spawn and publication with exit.
                // Exit can therefore never observe None and then leave a
                // newly spawned child behind.
                let mut guard = state.0.lock().unwrap();
                if INTENT_SHUTDOWN.load(Ordering::SeqCst) {
                    SUPERVISING.store(false, Ordering::SeqCst);
                    return;
                }
                match spawn_sidecar(&app) {
                    Ok(child) => {
                        *guard = Some(child);
                        true
                    }
                    Err(err) => {
                        eprintln!("SIDECAR_SPAWN_FAILED {err}");
                        false
                    }
                }
            };
            if spawned {
                loop {
                    std::thread::sleep(Duration::from_millis(300));
                    let mut guard = state.0.lock().unwrap();
                    match guard.as_mut() {
                        // The shutdown path took the child: we are done.
                        None => {
                            SUPERVISING.store(false, Ordering::SeqCst);
                            return;
                        }
                        Some(child) => match child.try_wait() {
                            Ok(Some(status)) => {
                                guard.take();
                                eprintln!("SIDECAR_EXITED status={status}");
                                break;
                            }
                            Ok(None) => {}
                            Err(err) => {
                                guard.take();
                                eprintln!("SIDECAR_WAIT_FAILED {err}");
                                break;
                            }
                        },
                    }
                }
            }
            if INTENT_SHUTDOWN.load(Ordering::SeqCst) {
                break;
            }
            attempts += 1;
            if attempts > MAX_RESTARTS {
                eprintln!("BACKEND_DOWN restarts_exhausted");
                // Make a retry issued by the event handler observable: the
                // new supervisor must not race a still-true state flag.
                SUPERVISING.store(false, Ordering::SeqCst);
                let _ = app.emit("backend-down", "restarts_exhausted");
                // Test-only hook: invoke the same command as the overlay,
                // but only from the exhaustion branch so backoff cannot be
                // mistaken for a backend-down transition.
                if std::env::var_os("SYNCBOX_RESTART_AFTER_EXHAUSTION").is_some() {
                    std::thread::sleep(Duration::from_millis(250));
                    let started = restart_sidecar(app.clone());
                    eprintln!("HARNESS_MANUAL_RESTART started={started}");
                }
                return;
            }
            let delay = BACKOFF_SECS[(attempts - 1) as usize];
            eprintln!("SIDECAR_RESTARTING attempt={attempts} backoff={delay}s");
            std::thread::sleep(Duration::from_secs(delay));
        }
        SUPERVISING.store(false, Ordering::SeqCst);
    });
    true
}

/// Manual "Relancer" after restart exhaustion (SPEC-DESIGN 5 backend-down
/// overlay). Starts a fresh supervisor (counter back to zero); the UI
/// confirms recovery through /health itself.
#[tauri::command]
fn restart_sidecar(app: tauri::AppHandle) -> bool {
    eprintln!("RESTART_SIDECAR_REQUESTED");
    INTENT_SHUTDOWN.store(false, Ordering::SeqCst);
    if app.state::<Sidecar>().0.lock().unwrap().is_some() {
        return false; // still running; nothing to do
    }
    start_supervisor(app)
}

/// Small bounded HTTP client for the two loopback lifecycle requests.
fn http_request(request: &str) -> Option<Vec<u8>> {
    let Ok(mut stream) = TcpStream::connect(SIDECAR_ADDR) else {
        return None;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    if stream.write_all(request.as_bytes()).is_err() {
        return None;
    }
    let mut response = Vec::new();
    stream.take(8192).read_to_end(&mut response).ok()?;
    Some(response)
}

fn http_status_body(response: &[u8]) -> Option<(u16, &[u8])> {
    let header_end = response.windows(4).position(|part| part == b"\r\n\r\n")?;
    let headers = std::str::from_utf8(&response[..header_end]).ok()?;
    let status = headers.lines().next()?.split_whitespace().nth(1)?.parse().ok()?;
    Some((status, &response[header_end + 4..]))
}

/// Exact protocol identity approved for stale-sidecar cleanup. This prevents
/// Syncbox from sending /shutdown to an unrelated service using port 8766.
fn syncbox_health() -> bool {
    let request = "GET /health HTTP/1.1\r\nHost: 127.0.0.1:8766\r\nConnection: close\r\n\r\n";
    let Some(response) = http_request(request) else {
        return false;
    };
    is_syncbox_health_response(&response)
}

fn is_syncbox_health_response(response: &[u8]) -> bool {
    let Some((200, body)) = http_status_body(&response) else {
        return false;
    };
    let Ok(payload) = serde_json::from_slice::<serde_json::Value>(body) else {
        return false;
    };
    payload
        == serde_json::json!({
            "ok": true,
            "service": "syncbox-sidecar",
            "protocol": 1
        })
}

fn post_shutdown() -> bool {
    let request = "POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:8766\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    http_request(request)
        .and_then(|response| http_status_body(&response).map(|(status, _)| status))
        == Some(202)
}

fn port_available() -> bool {
    TcpListener::bind(SIDECAR_ADDR).is_ok()
}

fn wait_port_available(timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if port_available() {
            return true;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    false
}

fn wait_exit(child: &mut Child, timeout: Duration) -> bool {
    let deadline = Instant::now() + timeout;
    while Instant::now() < deadline {
        if matches!(child.try_wait(), Ok(Some(_))) {
            return true;
        }
        std::thread::sleep(Duration::from_millis(50));
    }
    false
}

fn kill_group(pid: i32, signal: libc::c_int) {
    // killpg from a GUI-launched shell can return EPERM on macOS ->
    // direct-pid fallback (POC #2 recipe).
    if unsafe { libc::killpg(pid, signal) } != 0 {
        unsafe { libc::kill(pid, signal) };
    }
}

/// 6.6 handshake: shutdown command (closes SQLCipher cleanly) -> bounded
/// wait -> SIGTERM to the group -> SIGKILL to the group.
fn shutdown_sidecar(child: &mut Child) {
    let pid = child.id() as i32;
    if syncbox_health() && post_shutdown() && wait_exit(child, Duration::from_secs(4)) {
        eprintln!("SIDECAR_STOPPED clean");
        return;
    }
    kill_group(pid, libc::SIGTERM);
    if wait_exit(child, Duration::from_secs(2)) {
        eprintln!("SIDECAR_STOPPED sigterm");
        return;
    }
    kill_group(pid, libc::SIGKILL);
    let _ = child.wait();
    eprintln!("SIDECAR_STOPPED sigkill");
}

enum StartupPort {
    Available,
    Reaped,
    Blocked,
}

/// Stop only a sidecar carrying the exact approved protocol identity. A
/// foreign or unresponsive listener is preserved and reported as a collision.
fn reap_stale_sidecar() -> StartupPort {
    if port_available() {
        return StartupPort::Available;
    }
    if !syncbox_health() {
        return StartupPort::Blocked;
    }
    if post_shutdown() && wait_port_available(Duration::from_secs(5)) {
        eprintln!("STALE_SIDECAR_REAPED");
        StartupPort::Reaped
    } else {
        StartupPort::Blocked
    }
}

/// `tauri dev` runs a bare binary, so macOS shows the generic icon in the
/// Dock (bundle icons only apply to a packaged .app). Set it at runtime —
/// harmless in the bundle too, it just re-applies the same artwork.
#[cfg(target_os = "macos")]
fn set_dock_icon() {
    use objc2::{AllocAnyThread, MainThreadMarker};
    use objc2_app_kit::{NSApplication, NSImage};
    use objc2_foundation::NSData;

    let Some(mtm) = MainThreadMarker::new() else {
        return; // not the main thread: skip rather than crash
    };
    let data = NSData::with_bytes(include_bytes!("../icons/128x128@2x.png"));
    if let Some(image) = NSImage::initWithData(NSImage::alloc(), &data) {
        unsafe {
            NSApplication::sharedApplication(mtm).setApplicationIconImage(Some(&image));
        }
    }
}

fn main() {
    tauri::Builder::default()
        // Single-instance FIRST: a second launch self-exits before setup and
        // its callback (running in the primary) must never re-spawn a sidecar.
        .plugin(tauri_plugin_single_instance::init(|app, _args, _cwd| {
            eprintln!("SINGLE_INSTANCE_CALLBACK shell_pid={}", std::process::id());
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_opener::init())
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![restart_sidecar])
        .setup(|app| {
            eprintln!("PRIMARY_INSTANCE_STARTED shell_pid={}", std::process::id());
            #[cfg(target_os = "macos")]
            set_dock_icon();
            app.manage(Sidecar(Mutex::new(None)));
            match reap_stale_sidecar() {
                StartupPort::Available | StartupPort::Reaped => {
                    start_supervisor(app.handle().clone());
                }
                StartupPort::Blocked => {
                    eprintln!(
                        "PORT_COLLISION 127.0.0.1:8766 is occupied by a non-Syncbox service"
                    );
                    let handle = app.handle().clone();
                    std::thread::spawn(move || {
                        // Let the webview register its event listener first;
                        // status polling is the fallback if startup is slower.
                        std::thread::sleep(Duration::from_millis(500));
                        let _ = handle.emit("backend-down", "port_collision");
                    });
                }
            }
            // Harness hook: timed exit exercises the full shutdown handshake
            // without a window click (regression scripts in shell/harness/).
            if let Ok(secs) = std::env::var("SYNCBOX_EXIT_AFTER_SECS") {
                if let Ok(secs) = secs.parse::<u64>() {
                    let handle = app.handle().clone();
                    std::thread::spawn(move || {
                        std::thread::sleep(Duration::from_secs(secs));
                        handle.exit(0);
                    });
                }
            }
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("error while building the Syncbox shell")
        .run(|app, event| {
            if let tauri::RunEvent::Exit = event {
                // Intent flag BEFORE taking/killing (crash-vs-intent, 6.6);
                // taking the child also tells the supervisor to stand down.
                INTENT_SHUTDOWN.store(true, Ordering::SeqCst);
                let taken = app.state::<Sidecar>().0.lock().unwrap().take();
                if let Some(mut child) = taken {
                    shutdown_sidecar(&mut child);
                }
                eprintln!("SHUTDOWN intent=true");
            }
        });
}

#[cfg(test)]
mod tests {
    use super::{http_status_body, is_syncbox_health_response};

    #[test]
    fn parses_bounded_http_status_and_body() {
        let response = b"HTTP/1.1 202 Accepted\r\nContent-Length: 17\r\n\r\n{\"stopping\":true}";
        let (status, body) = http_status_body(response).expect("valid response");
        assert_eq!(status, 202);
        assert_eq!(body, b"{\"stopping\":true}");
    }

    #[test]
    fn rejects_malformed_http_responses() {
        assert!(http_status_body(b"").is_none());
        assert!(http_status_body(b"HTTP/1.1 nope\r\n\r\n").is_none());
        assert!(http_status_body(b"HTTP/1.1 200 OK\n\n{}").is_none());
    }

    #[test]
    fn accepts_only_the_exact_syncbox_health_identity() {
        let exact = b"HTTP/1.1 200 OK\r\n\r\n{\"ok\":true,\"service\":\"syncbox-sidecar\",\"protocol\":1}";
        assert!(is_syncbox_health_response(exact));
        assert!(!is_syncbox_health_response(
            b"HTTP/1.1 200 OK\r\n\r\n{\"ok\":true}"
        ));
        assert!(!is_syncbox_health_response(
            b"HTTP/1.1 200 OK\r\n\r\n{\"ok\":true,\"service\":\"syncbox-sidecar\",\"protocol\":2}"
        ));
    }
}
