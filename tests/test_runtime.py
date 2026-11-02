import asyncio
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from adapter.main import Controller, serve
from adapter.runtime import RuntimeGuard, RuntimeUnavailable, discover_runtime, process_identity
from test_controls import ControlFake

def fake_process(root,pid,start,state="S"):
    folder=Path(root)/str(pid)
    folder.mkdir(exist_ok=True)
    (folder/"comm").write_text("linuxcncsvr\n")
    (folder/"stat").write_text("%s (linuxcncsvr) %s %s %s\n" %
        (pid,state," ".join(["0"]*18),start))

class RuntimeTests(unittest.TestCase):
    def test_exit_pid_reuse_and_zombie_are_detected(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_process(temp,123,100)
            guard=RuntimeGuard.connect(temp)
            self.assertEqual(guard.identity,(123,100))
            guard.check()
            fake_process(temp,123,200)
            with self.assertRaises(RuntimeUnavailable):guard.check()
            fake_process(temp,123,200,"Z")
            self.assertIsNone(process_identity(123,temp))
            with self.assertRaises(RuntimeUnavailable):discover_runtime(temp)

    def test_wait_for_start_and_reject_multiple_instances(self):
        with tempfile.TemporaryDirectory() as temp:
            with self.assertRaises(RuntimeUnavailable):RuntimeGuard.connect(temp)
            fake_process(temp,100,10)
            fake_process(temp,200,20)
            with self.assertRaises(RuntimeUnavailable):RuntimeGuard.connect(temp)

    def test_restart_invalidates_authority_and_never_replays_commands(self):
        with tempfile.TemporaryDirectory() as temp:
            fake_process(temp,123,100)
            api=ControlFake()
            controller=Controller(api,temp)
            controller.runtime_guard=RuntimeGuard.connect(temp)
            controller.active={"U"};controller.owner="old"
            controller.programs=SimpleNamespace(ticket={"owner":"old"})
            controller.mdi_pending_serial=99
            fake_process(temp,123,200)
            for command in ("enable","estop","abort"):
                with self.assertRaises(RuntimeUnavailable):
                    controller.execute({"cmd":command,"session":"old"})
            self.assertEqual(api.calls,[])
            self.assertEqual(controller.active,set())
            self.assertIsNone(controller.owner)
            self.assertIsNone(controller.programs)
            self.assertIsNone(controller.mdi_pending_serial)
            replacement=Controller(api,temp)
            replacement.runtime_guard=RuntimeGuard.connect(temp)
            replacement.poll()
            self.assertEqual(api.calls,[])  # Reconnection itself never sends commands.

class RuntimeWatchdogTests(unittest.IsolatedAsyncioTestCase):
    async def exercise(self,runtime_lost):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/"adapter.sock"
            reason=[]
            controller=SimpleNamespace(active=set(),connection_failure=None,expire=lambda:None)
            controller.stop=lambda:None
            def invalidate(message):
                reason.append(message);controller.connection_failure=message
            controller.invalidate_connection=invalidate
            def runtime():
                if runtime_lost:raise RuntimeUnavailable("runtime changed")
            controller.check_runtime=runtime
            def poll():raise RuntimeError("NML unavailable")
            controller.poll=poll
            class Server:
                async def __aenter__(self):return self
                async def __aexit__(self,*args):pass
                async def serve_forever(self):await asyncio.Future()
            async def start(*args,**kwargs):
                path.write_text("")
                return Server()
            loop=asyncio.get_running_loop()
            with patch.object(loop,"add_signal_handler"), patch("adapter.main.asyncio.start_unix_server",start,create=True):
                with self.assertRaises(asyncio.CancelledError):
                    await serve(controller,str(path))
            self.assertTrue(reason)
            self.assertFalse(path.exists())
    async def test_runtime_change_stops_the_server(self):
        await self.exercise(True)
    async def test_repeated_idle_channel_errors_stop_the_server(self):
        await self.exercise(False)

if __name__=="__main__":unittest.main()
