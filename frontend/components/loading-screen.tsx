export function LoadingScreen() {
  return (
    <main className="loading-screen" aria-live="polite" aria-busy="true">
      <div className="spinner" />
      <p>Restoring your session…</p>
    </main>
  );
}
