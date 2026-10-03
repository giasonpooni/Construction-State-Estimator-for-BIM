"""Export the complete bounded raw belief to native fixed-Jacobian propagation."""
from .polyglot import linear_response_case


def uncertainty_inputs(world, outputs, deltas, *, input_scales, output_scales):
    """All raw variables participate; never pretend a selected marginal is full state."""
    inputs = list(world.belief.index.vars)
    if not 1 <= len(inputs) <= 8:
        raise ValueError("Full raw belief exceeds the 1..8 native coordinate budget")
    case = linear_response_case(world, inputs, outputs, deltas,
                                input_scales=input_scales, output_scales=output_scales)
    return {"schema": "notation.domain-uncertainty-inputs.v1", "case": case,
            "covariance_matrix": world.belief.sigma.tolist(),
            "source_evidence_ids": [], "source_covariance_ids": [],
            "assumptions": ["Complete raw belief, translated to delta coordinates about the current World means.",
                            "The current Jacobian is fixed; no relinearization at a changed mean.",
                            "This is propagated belief uncertainty, not independent field validation."]}
