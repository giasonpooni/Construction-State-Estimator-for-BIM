"""Required actual-World integration check; no dependency or fixture skips."""
from pathlib import Path
import unittest
import numpy as np
import gat
from gat.session import GatSession
from gat.adapters.polyglot import linear_response_case

class WorldIntegrationTests(unittest.TestCase):
    def test_shipped_ifc_world_exports_its_actual_raw_identity_tangent(self):
        session = GatSession.load_ifc(str(Path(gat.__file__).parent / "demo/beam_model.ifc"))
        world = session.world
        var = world.belief.index.vars[0]
        before = world.digest(); covariance = world.full.sigma.copy()
        row = list(world.full.index.vars).index(var)
        case = linear_response_case(world, [var], [var], [.001], input_scales=[1.], output_scales=[1.])
        self.assertEqual(case["jacobian_row_major"], [1.])
        self.assertEqual(case["baseline"], [float(world.full.mu[row])])
        self.assertEqual(case["model"]["digest"], "sha256:" + before)
        self.assertEqual(world.digest(), before)
        np.testing.assert_array_equal(world.full.sigma, covariance)

if __name__ == "__main__": unittest.main()
