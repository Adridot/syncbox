// POC #4 - SSE/EventSource inside the REAL WKWebView. Disposable.
// Bare Tauri v2 shell: loads the embedded ui/index.html (frontendDist), which on macOS
// gets the custom-protocol origin (tauri://localhost). The page drives all measurements
// and POSTs results to the loopback results server; no Rust logic is involved on purpose
// (the gate probes the webview transport, not the shell).
// Safety exit after 90 s so orchestration never hangs on a stuck window.

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                std::thread::sleep(std::time::Duration::from_secs(90));
                handle.exit(0);
            });
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
