"""Opt-in read-only test on a LinuxCNC host: FOAM_LINUXCNC_TEST=1."""
import os
from pathlib import Path
import unittest

@unittest.skipUnless(os.getenv("FOAM_LINUXCNC_TEST") == "1", "Requires running LinuxCNC; opt in explicitly")
class DevwingIntegrationTests(unittest.TestCase):
    def test_devwing_inverse_time_sample(self):
        import linuxcnc
        from adapter.preview import context_for
        from adapter.preview_worker import parse
        status = linuxcnc.stat()
        status.poll()
        sample = (Path(__file__).resolve().parent.parent / "examples/devwing-preview.nc").read_text()
        result = parse(context_for(status, sample))
        self.assertIn(len(result["segments"]), (14, 15))
        # Apply the live WCS transform to verify all four independent axes.
        import math
        p = {"X":26.0867,"Y":36.9684,"U":106.6841,"V":36.8073}
        scale = 1 if status.linear_units == 1 else 25.4
        p = {axis: value/scale for axis, value in p.items()}
        x,y = p["X"]+status.g92_offset[0],p["Y"]+status.g92_offset[1]
        angle = math.radians(status.rotation_xy)
        expected = [x*math.cos(angle)-y*math.sin(angle)+status.g5x_offset[0],
                    x*math.sin(angle)+y*math.cos(angle)+status.g5x_offset[1],
                    p["U"]+status.g92_offset[6]+status.g5x_offset[6],
                    p["V"]+status.g92_offset[7]+status.g5x_offset[7]]
        self.assertEqual(result["units"], "mm")
        scale = 1 if status.linear_units == 1 else 25.4
        for actual, target in zip(result["segments"][-1]["end"],expected):
            self.assertAlmostEqual(actual,target*scale,places=3)

if __name__ == "__main__":
    unittest.main()
