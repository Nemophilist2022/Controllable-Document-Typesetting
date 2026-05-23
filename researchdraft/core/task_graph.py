from __future__ import annotations

from .state import Stage


NEXT_STAGE = {
    Stage.INIT: Stage.INTERVIEWING,
    Stage.INTERVIEWING: Stage.PLANNING,
    Stage.PLANNING: Stage.DRAFTING,
    Stage.DRAFTING: Stage.FORMATTING,
    Stage.FORMATTING: Stage.VERIFYING,
    Stage.VERIFYING: Stage.DONE,
}


def next_stage(stage: Stage) -> Stage:
    return NEXT_STAGE[stage]

