"""Actual shipped-IFC World exports, with full covariance and no mutation."""
from pathlib import Path
from types import SimpleNamespace
import unittest
import numpy as np
import gat
from gat.session import GatSession
from gat.adapters.polyglot_uncertainty import uncertainty_inputs

class CompleteBeliefTests(unittest.TestCase):
    def setUp(self):
        self.world=GatSession.load_ifc(str(Path(gat.__file__).parent/'demo/beam_model.ifc')).world

    def test_all_raw_axes_and_full_covariance(self):
        w=self.world; n=w.binding.n_raw; outputs=list(w.full.index.vars)[-2:]
        before=w.digest()
        result=uncertainty_inputs(w,outputs,[0.]*n,input_scales=[1.]*n,output_scales=[1e6]*2)
        self.assertEqual(len(result['case']['inputs']),n)
        np.testing.assert_array_equal(result['covariance_matrix'],w.belief.sigma)
        self.assertEqual(w.digest(),before)
        result['covariance_matrix'][0][0]=999.
        self.assertNotEqual(w.belief.sigma[0,0],999.)

    def test_identity_and_derived_quantity_response(self):
        w=self.world; n=w.binding.n_raw
        result=uncertainty_inputs(w,list(w.full.index.vars)[-2:],[0.]*n,input_scales=[1.]*n,output_scales=[1e6]*2)
        self.assertEqual(result['case']['model']['digest'],'sha256:'+w.digest())
        j=np.asarray(result['case']['jacobian_row_major']).reshape(2,n)
        np.testing.assert_array_equal(j,w.jacobian[-2:])
        np.testing.assert_allclose(j@w.belief.sigma@j.T,w.full.sigma[-2:,-2:],rtol=1e-14)

    def test_larger_belief_is_not_truncated(self):
        world=SimpleNamespace(belief=SimpleNamespace(index=SimpleNamespace(vars=list(range(9)))))
        with self.assertRaisesRegex(ValueError,'budget'):
            uncertainty_inputs(world,[],[],input_scales=[],output_scales=[])

    def test_partial_delta_is_refused(self):
        with self.assertRaises(ValueError):
            uncertainty_inputs(self.world,[self.world.full.index.vars[0]],[0.],input_scales=[1.],output_scales=[1.])

if __name__=='__main__':unittest.main()
