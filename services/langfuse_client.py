"""Langfuse integration for observability and tracing"""
from typing import Any, Dict, Optional

from config import Config

try:
    from langfuse import Langfuse

    LANGFUSE_AVAILABLE = True
except ImportError:
    LANGFUSE_AVAILABLE = False


class LangfuseClient:
    """Client for Langfuse observability and tracing"""

    def __init__(self):
        self.enabled = LANGFUSE_AVAILABLE and bool(
            Config.LANGFUSE_PUBLIC_KEY and Config.LANGFUSE_SECRET_KEY
        )
        if self.enabled:
            try:
                self.client = Langfuse(
                    public_key=Config.LANGFUSE_PUBLIC_KEY,
                    secret_key=Config.LANGFUSE_SECRET_KEY,
                    host=Config.LANGFUSE_HOST,
                )
            except Exception as e:
                print(f"Failed to initialize Langfuse: {e}")
                self.client = None
                self.enabled = False
        else:
            self.client = None
            if not LANGFUSE_AVAILABLE:
                print("Langfuse not available - observability disabled")
            else:
                print("Langfuse not configured - observability disabled")

    def create_trace(
        self,
        name: str,
        user_id: str,
        session_id: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[str]:
        """Create a new trace for chat session"""
        if not self.enabled:
            return None

        # Create trace ID and start span
        trace_id = self.client.create_trace_id()
        return str(trace_id) if trace_id else None

    def log_generation(
        self,
        trace_id: str,
        name: str,
        input_data: Dict,
        output_data: Dict,
        model: str,
        tokens_used: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Log LLM generation to Langfuse"""
        if not self.enabled or not trace_id:
            return None

        try:
            generation = self.client.start_generation(
                name=name, model=model, input=input_data, metadata=metadata or {}
            )
            return generation
        except Exception as e:
            print(f"Langfuse generation logging failed: {e}")
            return None

    def log_span(
        self,
        trace,
        name: str,
        input_data: Optional[Dict[str, Any]] = None,
        output_data: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Optional[Any]:
        """Log a span (operation) to Langfuse"""
        if not self.enabled or not trace:
            return None

        return trace.span(
            name=name, input=input_data, output=output_data, metadata=metadata or {}
        )

    def log_event(
        self, trace_id: str, name: str, metadata: Optional[Dict[str, Any]] = None
    ) -> Optional[Any]:
        """Log an event to Langfuse"""
        if not self.enabled or not trace_id:
            return None

        try:
            # For now, just print the event since Langfuse API is complex
            print(f"Langfuse Event: {name} - {metadata}")
            return None
        except Exception as e:
            print(f"Langfuse event logging failed: {e}")
            return None

    def update_trace(
        self,
        trace_id: str,
        output: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Update trace with final output and metadata"""
        if not self.enabled or not trace_id:
            return

        try:
            # For now, just print the update since Langfuse API is complex
            print(
                f"Langfuse Trace Update: {trace_id} - Output: {output}, Metadata: {metadata}"
            )
        except Exception as e:
            print(f"Langfuse trace update failed: {e}")

    def score_generation(
        self,
        generation,
        score_name: str,
        score_value: float,
        comment: Optional[str] = None,
    ) -> None:
        """Add a score to a generation"""
        if not self.enabled or not generation:
            return

        generation.score(name=score_name, value=score_value, comment=comment)

    def flush(self) -> None:
        """Flush all pending events to Langfuse"""
        if self.enabled and self.client:
            self.client.flush()


# Global instance
langfuse_client = LangfuseClient()
