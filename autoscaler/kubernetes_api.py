"""Kubernetes API adapter placeholder."""


from kubernetes import client, config
from kubernetes.config.config_exception import ConfigException

def load_cluster_config() -> None:
    """Load Kubernetes cluster configuration."""
    try:
        config.load_incluster_config()
    except ConfigException:
        config.load_kube_config()

def get_current_replicas(namespace: str, deployment: str) -> int:
    """Get the current number of replicas for a deployment."""
    api = client.AppsV1Api()
    dep = api.read_namespaced_deployment(deployment, namespace)
    return dep.spec.replicas or 1

def set_replicas(namespace: str, deployment: str, replicas: int) -> None:
    """Set the number of replicas for a deployment."""
    api = client.AppsV1Api()
    body = {"spec": {"replicas": replicas}}
    api.patch_namespaced_deployment_scale(
        deployment,
        namespace,
        body
    )
