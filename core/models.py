from django.db import models
from django.contrib.auth.models import User


class ConversationThread(models.Model):
    """
    Stores conversational history threads for history tracking and chat organization.
    For authenticated users, threads persist permanently and are accessible across devices.
    For guest sessions, threads are ephemeral and automatically cleared on page reload.
    """
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="threads")
    session_id = models.CharField(max_length=128, unique=True, db_index=True)
    title = models.CharField(max_length=255, default="New Conversation")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    turns = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Conversation Thread"
        verbose_name_plural = "Conversation Threads"

    def __str__(self):
        return f"{self.title} ({self.session_id})"


class AgentProfileMemory(models.Model):
    """
    Sterilized, typed, and schema-bounded profile memory for Spider AI.
    Bound to session state without requiring user authentication.
    Prevents hallucination cascades, context bloat, and adversarial outbursts
    by storing structured entities, domain authority, and operational policies.
    """
    session_id = models.CharField(max_length=128, unique=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # 1. Last Concrete Primary Subject investigated (e.g. 'Kinetics', 'Sirai House')
    # Enables zero-shot anaphora resolution ('tell me more about it', 'introductory course on it')
    last_subject = models.CharField(max_length=255, blank=True, default="")

    # 2. Active Working Entities (e.g. ['M-KOPA', 'Apollo Agriculture', 'Pay Hero Kenya'])
    # Preserves concrete subjects across consecutive conversational turns
    active_entities = models.JSONField(default=list, blank=True)

    # 2. Experiential Domain Reputation Graph (domain -> reliability score, e.g. 'museums.co.ke': 95)
    domain_reputation = models.JSONField(default=dict, blank=True)

    # 3. Suppressed / Blacklisted Targets (domains or entities verified as contrary or broken)
    blacklisted_entities = models.JSONField(default=list, blank=True)

    # 4. Operational Guardrails & Preferences (formatting and safety constraints)
    preferences = models.JSONField(default=dict, blank=True)

    # 5. Verified Knowledge Facts (curated empirical facts verified by discriminator)
    verified_knowledge = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "Agent Profile Memory"
        verbose_name_plural = "Agent Profile Memories"

    def __str__(self):
        return f"AgentProfileMemory(session={self.session_id}, entities={len(self.active_entities)})"
