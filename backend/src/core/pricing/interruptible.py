import signal
import threading


SIGNALS = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)


class InterruptHandler:
    """Context manager for graceful shutdown in long-running loops.

    Catches SIGINT (Ctrl+C), SIGTERM (kill/docker stop), and SIGHUP (terminal closed).
    Restores previous handlers on exit.

    When used from a non-main thread, signal registration is skipped
    (signals can only be handled in the main thread). The handler still
    works as a context manager but `interrupted` will never become True.

    Usage:
        with InterruptHandler() as handler:
            for item in items:
                if handler.interrupted:
                    break
                do_work(item)
    """

    def __init__(self):
        self.interrupted = False
        self.prev_handlers = {}

    def __enter__(self):
        self.interrupted = False
        if threading.current_thread() is threading.main_thread():
            for sig in SIGNALS:
                self.prev_handlers[sig] = signal.getsignal(sig)
                signal.signal(sig, self.on_signal)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        for sig, handler in self.prev_handlers.items():
            signal.signal(sig, handler)
        self.prev_handlers.clear()
        return False

    def on_signal(self, sig, frame):
        self.interrupted = True
        name = signal.Signals(sig).name
        print(f"\n  {name} received, finishing current batch...")
