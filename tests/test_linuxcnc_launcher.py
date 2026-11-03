"""Mesa-triggered launch policy without real hardware or processes."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch
from deploy import linuxcnc_launcher as launcher


class GateTests(unittest.TestCase):
    def test_stability_and_power_cycle(self):
        gate = launcher.PowerGate()
        self.assertFalse(gate.sample(True))
        self.assertFalse(gate.sample(False))
        self.assertFalse(gate.sample(True))
        self.assertTrue(gate.sample(True))
        self.assertFalse(gate.sample(True))
        for _ in range(3):
            self.assertFalse(gate.sample(False))
        self.assertFalse(gate.sample(True))
        self.assertTrue(gate.sample(True))

    def test_closed_axis_does_not_immediately_reopen(self):
        gate = launcher.PowerGate()
        gate.armed = False
        for _ in range(10):
            self.assertFalse(gate.sample(True))

    def test_existing_instance_or_lock_blocks_launch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            lock = root / 'lock'
            proc = root / 'proc'
            proc.mkdir()
            self.assertFalse(launcher.linuxcnc_busy(proc, lock))
            lock.touch()
            self.assertTrue(launcher.linuxcnc_busy(proc, lock))
            lock.unlink()
            (proc / '123').mkdir()
            (proc / '123/comm').write_text('linuxcncsvr')
            self.assertTrue(launcher.linuxcnc_busy(proc, lock))

    def test_active_child_is_not_probed_and_exit_does_not_retry(self):
        event = Mock()
        event.is_set.return_value = False
        ticks = []
        def wait(timeout):
            ticks.append(timeout)
            if len(ticks) >= 8:
                event.is_set.return_value = True
        event.wait.side_effect = wait
        child = Mock()
        child.poll.side_effect = [None, None, 0]
        config = {'mesa_ip': '10.10.10.10', 'ping': '/bin/ping',
                  'halcmd': '/usr/bin/halcmd', 'linuxcnc': '/usr/bin/linuxcnc', 'ini': '/home/cnc/cutter.ini'}
        with patch.object(launcher.threading, 'Event', return_value=event), \
             patch.object(launcher.signal, 'signal'), \
             patch.object(launcher, 'linuxcnc_busy', return_value=False), \
             patch.object(launcher, 'read_mesa_error', return_value=False), \
             patch.object(launcher, 'probe', return_value=True) as probe, \
             patch.object(launcher.subprocess, 'Popen', return_value=child) as start:
            launcher.supervise(config)
        start.assert_called_once_with(['/usr/bin/linuxcnc', '-r', '/home/cnc/cutter.ini'],
                                      cwd=str(Path('/home/cnc/cutter.ini').parent), stdin=launcher.subprocess.DEVNULL)
        self.assertEqual(probe.call_count, 6)  # eight ticks minus two active-child ticks
        child.terminate.assert_not_called()

    def test_stop_closes_owned_launcher(self):
        event = Mock()
        event.is_set.return_value = False
        handlers = {}
        child = Mock()
        child.poll.return_value = None
        ticks = []
        def wait(timeout):
            ticks.append(timeout)
            if len(ticks) == 3:
                handlers[launcher.signal.SIGTERM](None, None)
        def stop():
            event.is_set.return_value = True
        event.set.side_effect = stop
        event.wait.side_effect = wait
        config = {'mesa_ip': '10.10.10.10', 'ping': '/bin/ping',
                  'halcmd': '/usr/bin/halcmd', 'linuxcnc': '/usr/bin/linuxcnc', 'ini': '/home/cnc/cutter.ini'}
        with patch.object(launcher.threading, 'Event', return_value=event), \
             patch.object(launcher.signal, 'signal', side_effect=lambda sig, cb: handlers.update({sig: cb})), \
             patch.object(launcher, 'linuxcnc_busy', return_value=False), \
             patch.object(launcher, 'read_mesa_error', return_value=False), \
             patch.object(launcher, 'probe', return_value=True), \
             patch.object(launcher.subprocess, 'Popen', return_value=child):
            launcher.supervise(config)
        self.assertTrue(child.terminate.called)
        child.wait.assert_called_once_with(timeout=25)

    def test_hal_status_requires_exactly_one_valid_board(self):
        cases = [('', None), ('hm2_eth bit RW FALSE hm2_7i96s.0.io_error', False),
                 ('hm2_eth bit RW TRUE hm2_7i96s.0.io_error', True),
                 ('hm2_eth bit RW MAYBE hm2_7i96s.0.io_error', None),
                 ('hm2_eth bit RW TRUE hm2_7i96s.0.io_error\n'
                  'hm2_eth bit RW FALSE hm2_7i92.0.io_error', None)]
        for output, expected in cases:
            with self.subTest(output=output), patch.object(launcher.subprocess, 'run',
                    return_value=Mock(returncode=0, stdout=output)):
                self.assertIs(launcher.read_mesa_error('/usr/bin/halcmd'), expected)
        with patch.object(launcher.subprocess, 'run', side_effect=launcher.subprocess.TimeoutExpired('halcmd', 2)):
            self.assertIsNone(launcher.read_mesa_error('/usr/bin/halcmd'))

    def test_fault_confirmation_ignores_transient_and_unknown_values(self):
        health = launcher.MesaHealth()
        for value in (False, True, True, None, True, False, True, True):
            self.assertFalse(health.sample(value))
        self.assertTrue(health.sample(True))
        self.assertTrue(health.healthy_seen)

    def test_power_loss_reaps_old_instance_before_relaunch(self):
        event = Mock()
        event.is_set.return_value = False
        first, second = Mock(), Mock()
        first.poll.return_value = None
        second.poll.return_value = None
        calls = []
        def wait_child(timeout):
            calls.append('reaped')
            first.returncode = 0
            first.poll.return_value = 0
        first.wait.side_effect = wait_child
        ticks = []
        def tick(timeout):
            ticks.append(timeout)
            if len(ticks) >= 9:
                event.is_set.return_value = True
        event.wait.side_effect = tick
        children = iter((first, second))
        def start(*args, **kwargs):
            calls.append('start')
            return next(children)
        config = {'mesa_ip': '10.10.10.10', 'ping': '/bin/ping', 'halcmd': '/usr/bin/halcmd',
                  'linuxcnc': '/usr/bin/linuxcnc', 'ini': '/home/cnc/cutter.ini'}
        with patch.object(launcher.threading, 'Event', return_value=event), \
             patch.object(launcher.signal, 'signal'), \
             patch.object(launcher, 'linuxcnc_busy', return_value=False), \
             patch.object(launcher, 'probe', return_value=True), \
             patch.object(launcher, 'read_mesa_error', side_effect=[False, True, True, True, False, False]), \
             patch.object(launcher.subprocess, 'Popen', side_effect=start):
            launcher.supervise(config)
        self.assertEqual(calls[:3], ['start', 'reaped', 'start'])
        first.terminate.assert_called_once()
        first.wait.assert_called_once_with(timeout=25)

    def test_axis_close_requests_graceful_exit_before_waiting(self):
        child = Mock()
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            launcher.close_owned_linuxcnc(child, '/usr/bin/axis-remote')
        self.assertEqual(run.call_args.args[0], ['/usr/bin/axis-remote', '--quit'])
        child.terminate.assert_not_called()
        child.wait.assert_called_once_with(timeout=25)

    def test_shutdown_timeout_is_an_error(self):
        child = Mock()
        child.wait.side_effect = launcher.subprocess.TimeoutExpired('linuxcnc', 25)
        with self.assertRaisesRegex(RuntimeError, 'refusing to launch'):
            launcher.close_owned_linuxcnc(child, None)

    def test_probe_uses_bounded_ping_without_shell(self):
        with patch.object(launcher.subprocess, 'run', return_value=Mock(returncode=0)) as run:
            self.assertTrue(launcher.probe('10.10.10.10', '/bin/ping'))
        self.assertEqual(run.call_args.args[0],
                         ['/bin/ping', '-n', '-c', '1', '-W', '1', '10.10.10.10'])
        self.assertEqual(run.call_args.kwargs['timeout'], 3)


if __name__ == '__main__':
    unittest.main()
