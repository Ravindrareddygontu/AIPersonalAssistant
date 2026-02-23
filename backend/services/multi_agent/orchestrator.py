import logging
import time
from dataclasses import dataclass, field
from typing import List, Optional, Callable
from enum import Enum

log = logging.getLogger('multi_agent')


class AgentRole(Enum):
    DEBATER_PRO = "debater_pro"
    DEBATER_CON = "debater_con"
    ANALYST = "analyst"
    CREATIVE = "creative"
    CRITIC = "critic"
    MODERATOR = "moderator"
    CUSTOM = "custom"


@dataclass
class AgentPersona:
    name: str
    role: AgentRole
    system_prompt: str
    color: str = "#ffffff"

    @classmethod
    def debater_pro(cls, topic: str) -> 'AgentPersona':
        return cls(
            name="Advocate",
            role=AgentRole.DEBATER_PRO,
            system_prompt=f"You are arguing IN FAVOR of: {topic}. Be persuasive, use facts and logic. Keep responses concise (2-3 paragraphs max).",
            color="#4CAF50"
        )

    @classmethod
    def debater_con(cls, topic: str) -> 'AgentPersona':
        return cls(
            name="Challenger",
            role=AgentRole.DEBATER_CON,
            system_prompt=f"You are arguing AGAINST: {topic}. Be persuasive, use facts and logic. Keep responses concise (2-3 paragraphs max).",
            color="#f44336"
        )

    @classmethod
    def analyst(cls) -> 'AgentPersona':
        return cls(
            name="Analyst",
            role=AgentRole.ANALYST,
            system_prompt="You analyze arguments objectively. Identify strengths, weaknesses, and logical fallacies. Be fair to both sides.",
            color="#2196F3"
        )

    @classmethod
    def moderator(cls, topic: str) -> 'AgentPersona':
        return cls(
            name="Moderator",
            role=AgentRole.MODERATOR,
            system_prompt=f"You are the debate moderator for: {topic}. Keep things civil, introduce speakers, provide brief transitions. Be professional and neutral.",
            color="#9C27B0"
        )


@dataclass
class AgentMessage:
    agent_name: str
    content: str
    timestamp: float = field(default_factory=time.time)
    role: AgentRole = AgentRole.CUSTOM


@dataclass
class ConversationResult:
    topic: str
    messages: List[AgentMessage]
    total_time: float
    rounds_completed: int
    summary: Optional[str] = None


class MultiAgentOrchestrator:

    DEFAULT_ROUNDS = 3
    MAX_ROUNDS = 10

    def __init__(self, workspace: str, model: str = None):
        self.workspace = workspace
        self.model = model
        self._executor = None

    def _init_executor(self):
        if self._executor is None:
            from backend.services.auggie import AuggieExecutor
            self._executor = AuggieExecutor()

    def run_debate(
        self,
        topic: str,
        rounds: int = DEFAULT_ROUNDS,
        on_message: Callable[[AgentMessage], None] = None,
        with_moderator: bool = False
    ) -> ConversationResult:
        self._init_executor()
        rounds = min(rounds, self.MAX_ROUNDS)

        pro = AgentPersona.debater_pro(topic)
        con = AgentPersona.debater_con(topic)
        moderator = AgentPersona.moderator(topic) if with_moderator else None
        agents = [pro, con]

        messages: List[AgentMessage] = []
        start_time = time.time()

        log.info(f"[MULTI-AGENT] Starting debate on: {topic} ({rounds} rounds, moderator={with_moderator})")

        context = f"DEBATE TOPIC: {topic}\n\n"

        if with_moderator:
            intro = self._get_moderator_message(moderator, "introduction", topic, messages)
            if intro:
                messages.append(intro)
                if on_message:
                    on_message(intro)

        for round_num in range(rounds):
            if with_moderator and round_num > 0:
                transition = self._get_moderator_message(moderator, "transition", topic, messages, round_num + 1)
                if transition:
                    messages.append(transition)
                    if on_message:
                        on_message(transition)

            for agent in agents:
                if with_moderator:
                    intro_speaker = self._get_moderator_message(moderator, "introduce_speaker", topic, messages, agent_name=agent.name)
                    if intro_speaker:
                        messages.append(intro_speaker)
                        if on_message:
                            on_message(intro_speaker)

                prompt = self._build_prompt(agent, context, messages, round_num + 1)
                response = self._executor.execute(
                    message=prompt,
                    workspace=self.workspace,
                    model=self.model,
                    source='bot'
                )

                if response.success and response.content:
                    msg = AgentMessage(
                        agent_name=agent.name,
                        content=response.content.strip(),
                        role=agent.role
                    )
                    messages.append(msg)
                    context += f"\n{agent.name}: {msg.content}\n"

                    if on_message:
                        on_message(msg)

                    log.info(f"[MULTI-AGENT] {agent.name} responded ({len(msg.content)} chars)")
                else:
                    log.warning(f"[MULTI-AGENT] {agent.name} failed: {response.error}")

        total_time = time.time() - start_time

        if with_moderator:
            closing = self._get_moderator_message(moderator, "closing", topic, messages)
            if closing:
                messages.append(closing)
                if on_message:
                    on_message(closing)

        summary = self._generate_summary(topic, messages) if messages else None

        return ConversationResult(
            topic=topic,
            messages=messages,
            total_time=total_time,
            rounds_completed=rounds,
            summary=summary
        )

    def _get_moderator_message(
        self,
        moderator: AgentPersona,
        message_type: str,
        topic: str,
        messages: List[AgentMessage],
        round_num: int = None,
        agent_name: str = None
    ) -> Optional[AgentMessage]:
        if message_type == "introduction":
            prompt = f"[PERSONA: {moderator.name}]\n{moderator.system_prompt}\n\nProvide a brief (2-3 sentences) introduction to start this debate. Welcome the audience and introduce the topic."
        elif message_type == "transition":
            prompt = f"[PERSONA: {moderator.name}]\n{moderator.system_prompt}\n\nProvide a brief (1-2 sentences) transition to round {round_num}."
        elif message_type == "introduce_speaker":
            prompt = f"[PERSONA: {moderator.name}]\n{moderator.system_prompt}\n\nBriefly (1 sentence) introduce {agent_name} to speak next."
        elif message_type == "closing":
            prompt = f"[PERSONA: {moderator.name}]\n{moderator.system_prompt}\n\nProvide brief closing remarks (2-3 sentences) thanking the debaters and wrapping up."
        else:
            return None

        response = self._executor.execute(
            message=prompt,
            workspace=self.workspace,
            model=self.model,
            source='bot'
        )

        if response.success and response.content:
            return AgentMessage(
                agent_name=moderator.name,
                content=response.content.strip(),
                role=moderator.role
            )
        return None

    def _build_prompt(
        self,
        agent: AgentPersona,
        context: str,
        messages: List[AgentMessage],
        round_num: int
    ) -> str:
        prompt = f"[PERSONA: {agent.name}]\n{agent.system_prompt}\n\n"
        prompt += f"Round {round_num}.\n\n"

        if messages:
            prompt += "Previous discussion:\n"
            for msg in messages[-4:]:
                prompt += f"{msg.agent_name}: {msg.content[:500]}...\n\n" if len(msg.content) > 500 else f"{msg.agent_name}: {msg.content}\n\n"
            prompt += "\nNow respond as " + agent.name + ":"
        else:
            prompt += context + "\n\nMake your opening argument:"

        return prompt

    def _generate_summary(self, topic: str, messages: List[AgentMessage]) -> Optional[str]:
        if not messages:
            return None

        analyst = AgentPersona.analyst()
        discussion = "\n".join([f"{m.agent_name}: {m.content}" for m in messages])

        prompt = f"{analyst.system_prompt}\n\nDebate topic: {topic}\n\n{discussion}\n\nProvide a brief summary of key points from both sides:"

        response = self._executor.execute(
            message=prompt,
            workspace=self.workspace,
            model=self.model,
            source='bot'
        )

        return response.content.strip() if response.success else None

