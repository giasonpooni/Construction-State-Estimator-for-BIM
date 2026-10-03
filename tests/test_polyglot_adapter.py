"""Adapter unit tests with explicit in-memory World protocol doubles."""
import importlib.util
from pathlib import Path
from dataclasses import dataclass
from types import SimpleNamespace as NS
import unittest
import numpy as np

path = Path(__file__).resolve().parents[1] / "gat/adapters/polyglot.py"
spec = importlib.util.spec_from_file_location("polyglot_adapter_under_test", path)
p = importlib.util.module_from_spec(spec); spec.loader.exec_module(p)

@dataclass(frozen=True)
class Entity:
    ifc_class: str = "IfcWall"
    global_id: str = "fixture-guid"
@dataclass(frozen=True)
class Var:
    entity: Entity
    quantity: str


def fixture():
    a, b, area = [Var(Entity(), name) for name in ("Width", "Height", "Area")]
    world = NS(belief=NS(index=NS(vars=[a, b])),
               full=NS(index=NS(vars=[a, b, area]), mu=np.array([2., 3., 6.]), sigma=np.eye(3)),
               jacobian=np.array([[1., 0.], [0., 1.], [3., 2.]]),
               module=NS(slot=lambda var: NS(unit=NS(value="m2" if var == area else "m"))),
               digest=lambda: "a"*64)
    return world, a, b, area

class AdapterTests(unittest.TestCase):
    def test_real_matrix_selection_without_world_mutation(self):
        w,a,b,area = fixture(); before=w.full.mu.copy(); cov=w.full.sigma.copy()
        case=p.linear_response_case(w,[a,b],[area],[.1,.2],input_scales=[1,1],output_scales=[1])
        self.assertEqual(case["jacobian_row_major"],[3.,2.]); self.assertEqual(case["baseline"],[6.])
        self.assertEqual(case["outputs"][0]["unit"],"m2")
        self.assertEqual(case["model"]["digest"],"sha256:"+w.digest())
        self.assertEqual(case["covariance"],"not_propagated"); self.assertIs(case["may_authorize"],False)
        np.testing.assert_array_equal(w.full.mu,before); np.testing.assert_array_equal(w.full.sigma,cov)

    def test_reordered_selection(self):
        w,a,b,area=fixture()
        c=p.linear_response_case(w,[b,a],[area,a],[.2,.1],input_scales=[1,1],output_scales=[1,1])
        self.assertEqual(c["jacobian_row_major"],[2.,3.,0.,1.])

    def test_refuses_derived_input(self):
        w,a,b,area=fixture()
        with self.assertRaises(ValueError): p.linear_response_case(w,[area],[a],[.1],input_scales=[1],output_scales=[1])

    def test_refuses_missing_jacobian(self):
        w,a,_,_=fixture(); w.jacobian=None
        with self.assertRaises(ValueError): p.linear_response_case(w,[a],[a],[.1],input_scales=[1],output_scales=[1])

    def test_refuses_duplicate(self):
        w,a,_,_=fixture()
        with self.assertRaises(ValueError): p.linear_response_case(w,[a,a],[a],[.1,.2],input_scales=[1,1],output_scales=[1])

    def test_refuses_invalid_scalar(self):
        w,a,_,_=fixture()
        for x in (True,"1",np.bool_(True),float("inf"),float("nan")):
            with self.subTest(x=x),self.assertRaises(ValueError): p.linear_response_case(w,[a],[a],[x],input_scales=[1],output_scales=[1])

    def test_refuses_bad_scale_or_shape(self):
        w,a,_,_=fixture()
        for args in (([.1],[0]),([], [1]),([.1],[1e101])):
            with self.subTest(args=args),self.assertRaises(ValueError): p.linear_response_case(w,[a],[a],args[0],input_scales=args[1],output_scales=[1])

    def test_refuses_nonfinite_jacobian(self):
        w,a,_,_=fixture(); w.jacobian[0,0]=np.nan
        with self.assertRaises(ValueError): p.linear_response_case(w,[a],[a],[.1],input_scales=[1],output_scales=[1])

if __name__ == "__main__": unittest.main()
