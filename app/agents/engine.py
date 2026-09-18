import logging
from typing import Any, Callable, Coroutine
from app.agents.router import CognitiveMode
from app.agents.prompts import PLANNER_PROMPT, ANALYST_PROMPT, CRITIC_PROMPT, FINALIZER_PROMPT

class CognitiveEngine:
    """Orchestrates multi-agent workflows."""
    
    def __init__(self, run_model_callback: Callable[..., Coroutine[Any, Any, str]]):
        """
        run_model_callback should have the signature:
        async def run_model(messages, system_prompt, use_tools=False, on_chunk=None) -> str
        """
        self.run_model = run_model_callback
        self.log = logging.getLogger("jasper.agents.engine")

    async def run(self, mode: CognitiveMode, context_messages: list[dict[str, Any]], user_text: str, on_chunk: Callable[[str], None] | None = None) -> str:
        self.log.info("starting cognitive run mode=%s", mode.value)
        
        if mode == CognitiveMode.SIMPLE:
            return await self._run_simple(context_messages, user_text, on_chunk)
        elif mode == CognitiveMode.COLLABORATIVE:
            return await self._run_collaborative(context_messages, user_text, on_chunk)
        elif mode == CognitiveMode.DEEP:
            return await self._run_deep(context_messages, user_text, on_chunk)
            
        raise ValueError(f"Unknown cognitive mode: {mode}")

    async def _run_simple(self, context_messages: list[dict[str, Any]], user_text: str, on_chunk: Callable[[str], None] | None) -> str:
        messages = list(context_messages)
        messages.append({"role": "user", "content": user_text})
        return await self.run_model(messages, system_prompt=None, use_tools=True, mode=CognitiveMode.SIMPLE, user_text=user_text, on_chunk=on_chunk)

    async def _run_collaborative(self, context_messages: list[dict[str, Any]], user_text: str, on_chunk: Callable[[str], None] | None) -> str:
        # Planner Stage
        self.log.info("stage=planner starting")
        planner_msgs = list(context_messages)
        planner_msgs.append({"role": "user", "content": f"Create a plan for this request:\n\n{user_text}"})
        plan = await self.run_model(planner_msgs, system_prompt=PLANNER_PROMPT, use_tools=False, mode=CognitiveMode.COLLABORATIVE, user_text=user_text)
        self.log.info("stage=planner completed")

        # Finalizer Stage
        self.log.info("stage=finalizer starting")
        finalizer_msgs = list(context_messages)
        finalizer_msgs.append({"role": "user", "content": f"Request:\n{user_text}\n\nPlanner Output:\n{plan}"})
        answer = await self.run_model(finalizer_msgs, system_prompt=FINALIZER_PROMPT, use_tools=True, mode=CognitiveMode.COLLABORATIVE, user_text=user_text, on_chunk=on_chunk)
        self.log.info("stage=finalizer completed")
        
        return answer

    async def _run_deep(self, context_messages: list[dict[str, Any]], user_text: str, on_chunk: Callable[[str], None] | None) -> str:
        # Planner Stage
        self.log.info("stage=planner starting")
        planner_msgs = list(context_messages)
        planner_msgs.append({"role": "user", "content": f"Create a plan for this request:\n\n{user_text}"})
        plan = await self.run_model(planner_msgs, system_prompt=PLANNER_PROMPT, use_tools=False, mode=CognitiveMode.DEEP, user_text=user_text)
        self.log.info("stage=planner completed")

        # Analyst Stage
        self.log.info("stage=analyst starting")
        analyst_msgs = list(context_messages)
        analyst_msgs.append({"role": "user", "content": f"Request:\n{user_text}\n\nPlan to execute:\n{plan}"})
        evidence = await self.run_model(analyst_msgs, system_prompt=ANALYST_PROMPT, use_tools=True, mode=CognitiveMode.DEEP, user_text=user_text)
        self.log.info("stage=analyst completed")

        # Critic Stage
        self.log.info("stage=critic starting")
        critic_msgs = list(context_messages)
        critic_msgs.append({"role": "user", "content": f"Request:\n{user_text}\n\nPlan:\n{plan}\n\nAnalyst Evidence:\n{evidence}"})
        criticism = await self.run_model(critic_msgs, system_prompt=CRITIC_PROMPT, use_tools=False, mode=CognitiveMode.DEEP, user_text=user_text)
        self.log.info("stage=critic completed")

        # Finalizer Stage
        self.log.info("stage=finalizer starting")
        finalizer_msgs = list(context_messages)
        finalizer_msgs.append({"role": "user", "content": f"Request:\n{user_text}\n\nPlan:\n{plan}\n\nAnalyst Evidence:\n{evidence}\n\nCritic Issues:\n{criticism}"})
        answer = await self.run_model(finalizer_msgs, system_prompt=FINALIZER_PROMPT, use_tools=False, mode=CognitiveMode.DEEP, user_text=user_text, on_chunk=on_chunk)
        self.log.info("stage=finalizer completed")
        
        return answer
