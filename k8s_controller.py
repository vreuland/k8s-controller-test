import kopf
from kubernetes import client, config, watch
from config import Config
from kubernetes.client import AppsV1Api, V1Deployment

# Set up logging
logger = Config.setup_logging()

cluster = Config.cluster()


def kubeconfig() -> client.AppsV1Api:
    """This is for using the kubeconfig to auth with the k8s api
    with the first try it will try to use the in-cluster config (so for in cluster use)
    If it cannot find an incluster because it is running locally, it will use your local config"""
    try:
        # Try to load the in-cluster configuration
        config.load_incluster_config()
        logger.info("Loaded in-cluster configuration.")
    except config.ConfigException:
        # If that fails, fall back to kubeconfig file
        config.load_kube_config(context=cluster)
        logger.info(f"Loaded kubeconfig file with context {cluster}.")

        # Check the active context
        _, active_context = config.list_kube_config_contexts()
        if active_context:
            logger.info(f"The active context is {active_context['name']}.")
        else:
            logger.info("No active context.")

    # Now you can use the client
    api = client.AppsV1Api()
    return api


def watch_namespace_deployments(v1: AppsV1Api, namespace: str) -> None:
    """Watch deployments in a specified namespace"""
    logger.info(f"Watching namespace {namespace} on cluster {v1.api_client.configuration.host}")
    w = watch.Watch()
    for event in w.stream(v1.list_namespaced_deployment, namespace=namespace, timeout_seconds=10):
        process_deployment_event(event, v1)


def process_deployment_event(event: dict, v1: AppsV1Api) -> None:
    """Process pod events and take necessary actions"""
    if event['type'] not in ('ADDED', 'MODIFIED'):
        return

    logger.info(f"Event: {event['type']} Object: {event['object']}")
    add_host_aliases(event['object'], v1)


def add_host_aliases(deployment: V1Deployment, v1: AppsV1Api) -> None:
    logger.info("Adding host aliases")

    # HostAliases to add
    host_aliases_patch = {
        "spec": {
            "template": {
                "spec": {
                    "hostAliases": [
                        {
                            "ip": "127.0.0.1",
                            "hostnames": ["example.com", "test.local"]
                        }
                    ]
                }
            }
        }
    }

    try:
        # Patch the deployment
        response = v1.patch_namespaced_deployment(
            name=deployment.metadata.name,
            namespace=deployment.metadata.namespace,
            body=host_aliases_patch
        )
        logger.info(f"Patched deployment '{deployment.metadata.name}' with HostAliases.")
    except client.exceptions.ApiException as e:
        logger.error(f"Failed to patch deployment '{deployment.metadata.name}': {e}")


@kopf.on.startup()
def on_startup(**kwargs):
    """On startup, watch pods"""
    logger.info("Starting up")
    v1 = kubeconfig()
    watch_namespace_deployments(v1, Config.namespace)


@kopf.on.timer('deployments', interval=Config.interval)
def on_timer(**kwargs):
    """On timer, watch pods"""
    logger.info("Starting up")
    v1 = kubeconfig()
    watch_namespace_deployments(v1, Config.namespace)


def main():
    kopf.run(namespace=Config.namespace)


if __name__ == '__main__':
    main()