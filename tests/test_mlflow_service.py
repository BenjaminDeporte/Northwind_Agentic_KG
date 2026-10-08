from types import SimpleNamespace

from common.config.settings import MLflowSettings
from common.mlflow import MlflowRunService


class FakeRun:
    def __init__(self):
        self.info = SimpleNamespace(run_id="run-123")

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class FakeMlflow:
    def __init__(self):
        self.tracking_uri = None
        self.experiment = None
        self.params = None
        self.metrics = None
        self.artifacts = {}

    def set_tracking_uri(self, value):
        self.tracking_uri = value

    def set_experiment(self, value):
        self.experiment = value

    def start_run(self, **kwargs):
        self.run_kwargs = kwargs
        return FakeRun()

    def log_params(self, value):
        self.params = value

    def log_metrics(self, value):
        self.metrics = value

    def log_dict(self, value, path):
        self.artifacts[path] = value


def test_mlflow_service_logs_one_flat_run_and_raw_result():
    fake = FakeMlflow()
    service = MlflowRunService(
        MLflowSettings(tracking_uri="http://mlflow:5000", experiment_name="test-exp"),
        mlflow_module=fake,
    )
    result = service.log_result(
        runtime_metadata={
            "architecture": "generic",
            "conversational_model": "mistral-large-latest",
            "cypher_model": "gemma",
            "prompt_version": "generic-v1",
        },
        result={
            "question": "How many customers?",
            "answer": "There are 91.",
            "structured_result": {"customerCount": 91},
            "generated_cypher": ["MATCH (c:Customer) RETURN count(c)"],
            "validation_attempts": [{"status": "valid"}],
            "neo4j_results": [{"status": "ok", "rows": [{"values": {"customerCount": 91}}]}],
            "loop_count": 1,
            "error": None,
        },
        prompts={"schema_prompt": "### Schema\n(:Customer)"},
        run_name="acceptance",
    )

    assert result.run_id == "run-123"
    assert fake.tracking_uri == "http://mlflow:5000"
    assert fake.experiment == "test-exp"
    assert fake.run_kwargs["run_name"] == "acceptance"
    assert fake.params["architecture"] == "generic"
    assert fake.metrics["neo4j_row_count"] == 1.0
    assert fake.artifacts["runtime_result.json"]["structured_result"] == {"customerCount": 91}
    assert fake.artifacts["prompts.json"]["schema_prompt"].startswith("### Schema")
