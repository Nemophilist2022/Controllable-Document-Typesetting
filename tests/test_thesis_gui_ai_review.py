"""B3 — GUI 的 AI 评测按钮 + 完成度报告窗口。

我们不真正起 Tk 主循环，而是 mock 掉 mainloop 并通过线程同步等待
worker 完成。两条测试覆盖：

1. 没选输入文件时弹 warning，不调 harness。
2. 跑 eval_only 后调用了 harness.run，并产出 RunResult。
   _show_ai_report 用 Toplevel 简单测试：能创建出 widget。
"""

import sys
import tempfile
import threading
import time
import tkinter
import unittest
from pathlib import Path
from unittest import mock

from docx import Document


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


_ORIGINAL_MAINLOOP = tkinter.Misc.mainloop


def _make_minimal_doc(path):
    d = Document()
    d.add_paragraph("第一段", style="Normal")
    d.save(path)


class FormatterGUIAIReviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tkinter.Misc.mainloop = lambda self, n=0: None

    @classmethod
    def tearDownClass(cls):
        tkinter.Misc.mainloop = _ORIGINAL_MAINLOOP

    def setUp(self):
        import thesis_gui

        self.thesis_gui = thesis_gui
        self.gui = thesis_gui.FormatterGUI(theme="sandstone")

    def tearDown(self):
        try:
            self.gui._root.destroy()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # No input → warning, harness not invoked
    # ------------------------------------------------------------------

    def test_ai_review_without_input_warns_and_skips(self):
        self.gui._v_in.set("")  # no input

        # Patch the messagebox helper the GUI already exposes.
        with mock.patch.object(self.gui, "_messagebox") as msgbox, \
             mock.patch("thesis_agent.orchestrator.harness.run") as harness_run:
            self.gui._start_ai_review()
            msgbox.showwarning.assert_called_once()
            harness_run.assert_not_called()

    # ------------------------------------------------------------------
    # Happy path — harness called with mode=eval_only and llm_disabled
    # ------------------------------------------------------------------

    def test_ai_review_invokes_harness_with_eval_only_and_no_llm(self):
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "x.docx"
            _make_minimal_doc(in_path)
            self.gui._v_in.set(str(in_path))

            done = threading.Event()
            captured = {}

            def fake_run(*, input_path, profile, mode, options):
                captured["input_path"] = input_path
                captured["profile"] = profile
                captured["mode"] = mode
                captured["options"] = options
                # The GUI calls _show_ai_report on the tkinter main
                # thread via root.after. We sidestep the visual report
                # by also patching that method below.
                done.set()

                class _R:
                    summary = {"total": 0, "done": 0, "partial": 0,
                                "failed": 0, "skipped": 0}
                    report_md_path = "/x/r.md"
                    report_json_path = "/x/r.json"
                    trace_path = "/x/t.jsonl"
                    docx_path = None
                    pending_path = None
                    exit_reason = "ok"
                    ok = True
                return _R()

            with mock.patch(
                "thesis_agent.orchestrator.harness.run",
                side_effect=fake_run,
            ), mock.patch.object(
                self.gui, "_show_ai_report"
            ) as show_report:
                self.gui._start_ai_review()
                # The worker thread completes asynchronously; wait up
                # to 5 seconds for it.
                self.assertTrue(done.wait(5.0),
                                msg="harness.run was never called")
                # Drain pending root.after callbacks so _show_ai_report
                # gets dispatched.
                for _ in range(10):
                    self.gui._root.update_idletasks()
                    self.gui._root.update()
                    if show_report.called:
                        break
                    time.sleep(0.05)

            self.assertEqual(captured["mode"], "eval_only")
            self.assertEqual(captured["profile"], "scau_2024")
            self.assertEqual(captured["input_path"], str(in_path))
            self.assertTrue(captured["options"].llm_disabled)
            self.assertEqual(captured["options"].auto_apply_diagnosis, "no")

    # ------------------------------------------------------------------
    # GUI worker race — when the root window is gone before the worker
    # tries to schedule UI updates, we must NOT raise.
    # ------------------------------------------------------------------

    def test_ai_review_worker_swallows_runtime_error_after_root_destroyed(self):
        """Reproduces the unittest tearDown race: worker thread is still
        in flight when the test destroys ``self._root``. Subsequent
        ``self._root.after(...)`` calls would otherwise raise
        ``RuntimeError: main thread is not in main loop`` and pollute
        stderr with a traceback for every GUI test that ran after one
        of these.
        """
        with tempfile.TemporaryDirectory() as tmp:
            in_path = Path(tmp) / "x.docx"
            _make_minimal_doc(in_path)
            self.gui._v_in.set(str(in_path))

            started = threading.Event()
            allow_finish = threading.Event()
            uncaught: list = []

            def fake_run(*, input_path, profile, mode, options):
                started.set()
                # Block until the test signals we may proceed; this
                # gives the test time to destroy the root.
                allow_finish.wait(2.0)

                class _R:
                    summary = {"total": 0, "done": 0, "partial": 0,
                                "failed": 0, "skipped": 0}
                    report_md_path = "/x/r.md"
                    report_json_path = "/x/r.json"
                    trace_path = "/x/t.jsonl"
                    docx_path = None
                    pending_path = None
                    exit_reason = "ok"
                    ok = True
                return _R()

            # Capture any uncaught exception escaping the worker.
            real_excepthook = threading.excepthook

            def hook(args):
                uncaught.append(args)

            threading.excepthook = hook
            try:
                with mock.patch(
                    "thesis_agent.orchestrator.harness.run",
                    side_effect=fake_run,
                ), mock.patch.object(self.gui, "_show_ai_report"):
                    self.gui._start_ai_review()
                    self.assertTrue(started.wait(2.0),
                                    msg="worker never started")
                    # Pull the rug: destroy the root WHILE the worker
                    # is still inside fake_run.
                    self.gui._root.destroy()
                    allow_finish.set()
                    # Give the worker a moment to finish + its safe_after
                    # calls to no-op.
                    time.sleep(0.3)
            finally:
                threading.excepthook = real_excepthook

            self.assertEqual(uncaught, [],
                             msg=f"worker raised: {uncaught}")


if __name__ == "__main__":
    unittest.main()
