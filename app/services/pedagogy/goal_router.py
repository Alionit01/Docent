from app.schemas.schemas import GoalType
from app.services.llm.prompts import GOAL_PROMPTS


def get_goal_instruction(goal_type: GoalType) -> str:
    return GOAL_PROMPTS.get(goal_type, GOAL_PROMPTS["understand"])
