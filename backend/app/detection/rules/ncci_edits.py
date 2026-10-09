from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import NCCI_BYPASS_MODIFIERS, NCCI_PAIRS


class NCCIEdits(Rule):
    name = "ncci_edit"
    description = "A comprehensive code and one of its component codes billed together without a distinct-service modifier."

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        by_code = {l.cpt_code: l for l in ctx.claim.lines if l.cpt_code}
        hits = []
        for comprehensive, component in NCCI_PAIRS:
            if comprehensive in by_code and component in by_code:
                if not set(by_code[component].modifiers) & NCCI_BYPASS_MODIFIERS:
                    hits.append({"comprehensive": comprehensive, "component": component, "component_billed": by_code[component].billed_amount})
        if not hits:
            return None
        return self.signal(
            min(0.9, 0.7 + 0.08 * len(hits)),
            {"edit_pairs": hits, "edit_source": "Illustrative NCCI procedure-to-procedure sample"},
            ["lines.cpt_code", "lines.modifiers"],
        )
