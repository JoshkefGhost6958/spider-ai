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


class SiteWatchTarget(models.Model):
    """
    Monitored website target tracked by Spider AI autonomous monitoring suite.
    Tracks uptime health, latency, content hashes, title, and alert rules.
    """
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="site_monitors")
    session_id = models.CharField(max_length=128, db_index=True)
    url = models.URLField(max_length=512)
    label = models.CharField(max_length=255, blank=True, default="")
    watch_type = models.CharField(max_length=50, default="health_and_content")  # health, content, feed, keyword
    keyword = models.CharField(max_length=255, blank=True, default="")
    interval_seconds = models.PositiveIntegerField(default=3600)

    # Live snapshot tracking
    last_status_code = models.IntegerField(null=True, blank=True)
    last_latency_ms = models.FloatField(null=True, blank=True)
    last_content_hash = models.CharField(max_length=64, blank=True, default="")
    last_title = models.CharField(max_length=512, blank=True, default="")
    last_checked_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    metadata = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Site Watch Target"
        verbose_name_plural = "Site Watch Targets"

    def __str__(self):
        return f"{self.label or self.url} ({self.watch_type})"


class SiteNotificationAlert(models.Model):
    """
    Alert notification emitted by the site monitoring engine.
    Displayed inside the top navbar notification bell drawer.
    """
    user = models.ForeignKey(User, null=True, blank=True, on_delete=models.CASCADE, related_name="site_alerts")
    session_id = models.CharField(max_length=128, db_index=True)
    target = models.ForeignKey(SiteWatchTarget, null=True, blank=True, on_delete=models.CASCADE, related_name="alerts")
    title = models.CharField(max_length=255)
    message = models.TextField()
    alert_level = models.CharField(max_length=30, default="info")  # info, warning, critical, success
    url = models.URLField(max_length=512, blank=True, default="")
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    details = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Site Notification Alert"
        verbose_name_plural = "Site Notification Alerts"

    def __str__(self):
        return f"[{self.alert_level.upper()}] {self.title}"
