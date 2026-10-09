from app.detection.context import DetectionContext, Signal
from app.detection.rules.base import Rule
from app.utils.codes import PANELS


class Unbundling(Rule):
    name = "unbundling"
    description = "Component tests billed separately where a single panel code applies."
    min_components = 4

    def evaluate(self, ctx: DetectionContext) -> Signal | None:
        codes = set(ctx.claim.cpt_codes)
        best: tuple[str, set[str]] | None = None
        for panel, components in PANELS.items():
            billed = codes & components
            if panel not in codes and len(billed) >= self.min_components and (best is None or len(billed) > len(best[1])):
                best = (panel, billed)
        if best is None:
            return None
        panel, billed = best
        billed_amount = sum(l.billed_amount for l in ctx.claim.lines if l.cpt_code in billed)
        confidence = 0.90 + 0.08 * len(billed) / len(PANELS[panel])
        return self.signal(
            confidence,
            {"panel_code": panel, "components_billed": sorted(billed), "components_in_panel": len(PANELS[panel]), "billed_for_components": round(billed_amount, 2)},
            ["lines.cpt_code", "lines.billed_amount"],
        )
