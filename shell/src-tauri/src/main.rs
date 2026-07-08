// Syncbox shell supervisor. Order is load-bearing (POC #2 / SPEC-UNIFIED 6.6):
// single-instance registered FIRST (second launch self-exits, callback never
// re-spawns); sidecar spawned in its OWN process group (pgid == pid, killpg
// safe); child output always consumed; crash vs intent decided by a flag set
// BEFORE any kill (exit codes cannot discriminate - POC #2 T6); bounded
// restart 3x backoff 1/2/4 s then a `backend-down` event to the UI; manual
// `restart_sidecar` command after exhaustion; shutdown handshake on exit =
// POST /shutdown -> bounded wait -> SIGTERM group -> SIGKILL group.
//
// macOS-only code paths for now; Windows (taskkill /T, mutex) is pre-M5 work.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpStream;
use std::os::unix::process::CommandExt;
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use tauri::{Emitter, Manager};

const SIDECAR_ADDR: (&str, u16) = ("127.0.0.1", 8765);
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
                for line in BufReader::new(stream).lines().map_while(Result::ok) {
                    eprintln!("[sidecar:{name}] {line}");
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
fn start_supervisor(app: tauri::AppHandle) {
    if SUPERVISING.swap(true, Ordering::SeqCst) {
        return; // already supervising
    }
    std::thread::spawn(move || {
        // ponytail: the strike counter never auto-resets; 3 crashes over the
        // app's lifetime -> backend-down + manual "Relancer" (which starts a
        // fresh supervisor). Add uptime-based reset only if it bites.
        let mut attempts: u32 = 0;
        loop {
            match spawn_sidecar(&app) {
                Ok(child) => {
                    let state = app.state::<Sidecar>();
                    *state.0.lock().unwrap() = Some(child);
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
                                _ => {}
                            },
                        }
                    }
                }
                Err(err) => eprintln!("SIDECAR_SPAWN_FAILED {err}"),
            }
            if INTENT_SHUTDOWN.load(Ordering::SeqCst) {
                break;
            }
            attempts += 1;
            if attempts > MAX_RESTARTS {
                eprintln!("BACKEND_DOWN restarts_exhausted");
                let _ = app.emit("backend-down", ());
                break;
            }
            let delay = BACKOFF_SECS[(attempts - 1) as usize];
            eprintln!("SIDECAR_RESTARTING attempt={attempts} backoff={delay}s");
            std::thread::sleep(Duration::from_secs(delay));
        }
        SUPERVISING.store(false, Ordering::SeqCst);
    });
}

/// Manual "Relancer" after restart exhaustion (SPEC-DESIGN 5 backend-down
/// overlay). Starts a fresh supervisor (counter back to zero); the UI
/// confirms recovery through /health itself.
#[tauri::command]
fn restart_sidecar(app: tauri::AppHandle) {
    eprintln!("RESTART_SIDECAR_REQUESTED");
    INTENT_SHUTDOWN.store(false, Ordering::SeqCst);
    if app.state::<Sidecar>().0.lock().unwrap().is_some() {
        return; // still running; nothing to do
    }
    start_supervisor(app);
}

/// Best-effort POST /shutdown over a raw socket (stdlib only; no HTTP crate
/// for one loopback request). Returns true if the sidecar answered.
fn post_shutdown() -> bool {
    let Ok(mut stream) = TcpStream::connect(SIDECAR_ADDR) else {
        return false;
    };
    let _ = stream.set_read_timeout(Some(Duration::from_secs(2)));
    let _ = stream.set_write_timeout(Some(Duration::from_secs(2)));
    let request = "POST /shutdown HTTP/1.1\r\nHost: 127.0.0.1:8765\r\nContent-Length: 0\r\nConnection: close\r\n\r\n";
    if stream.write_all(request.as_bytes()).is_err() {
        return false;
    }
    let mut buf = [0u8; 64];
    stream.read(&mut buf).is_ok()
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
    if post_shutdown() && wait_exit(child, Duration::from_secs(4)) {
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

/// An orphaned sidecar from a previous shell crash still holds :8765 and
/// would make this launch fail its port check. Ask it to stop first.
fn reap_stale_sidecar() {
    if post_shutdown() {
        eprintln!("STALE_SIDECAR_REAPED");
        std::thread::sleep(Duration::from_millis(500));
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
            reap_stale_sidecar();
            app.manage(Sidecar(Mutex::new(None)));
            start_supervisor(app.handle().clone());
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
