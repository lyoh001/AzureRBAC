from azure.storage.blob import BlobServiceClient
from azure.servicebus import ServiceBusClient, ServiceBusMessage
import azure.functions as func
import logging
import os
import requests


def get_rest_api_token():
    try:
        oauth2_headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        oauth2_body = {
            "client_id": os.environ["REST_CLIENT_ID"],
            "client_secret": os.environ["REST_CLIENT_SECRET"],
            "grant_type": "client_credentials",
            "resource": "https://management.azure.com"
        }
        oauth2_url = f"https://login.microsoftonline.com/{os.environ['TENANT_ID']}/oauth2/token"
        return requests.post(url=oauth2_url, headers=oauth2_headers, data=oauth2_body).json()["access_token"]

    except Exception as e:
        logging.info(str(e))

def get_graph_api_token():
    try:
        oauth2_headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        oauth2_body = {
            "client_id": os.environ["GRAPH_CLIENT_ID"],
            "client_secret": os.environ["GRAPH_CLIENT_SECRET"],
            "grant_type": "client_credentials",
            "scope": "https://graph.microsoft.com/.default"
        }
        oauth2_url = f"https://login.microsoftonline.com/{os.environ['TENANT_ID']}/oauth2/v2.0/token"
        return requests.post(url=oauth2_url, headers=oauth2_headers, data=oauth2_body).json()["access_token"]

    except Exception as e:
        logging.info(str(e))

def main(mytimer: func.TimerRequest) -> None:
    # debugging start the function
    logging.info("-------------------------------------------------------------------------------------")
    logging.info(f"******* Generating weekly Azure rbac report *******")

    # constructing API headers and variables
    rest_api_headers = {"Authorization": f"Bearer {get_rest_api_token()}", "Content-Type": "application/json"}
    graph_api_headers = {"Authorization": f"Bearer {get_graph_api_token()}", "Host": "graph.microsoft.com"}
    logging.info("-------------------------------------------------------------------------------------")
    logging.info(f"******* Completed constructing API headers *******")

    # cleaning up AAD Guest RBAC Review
    try:
        members = requests.get(url="https://graph.microsoft.com/v1.0/groups/c6f8666e-053a-4f09-a15c-6feee253af06/members", headers=graph_api_headers).json()["value"]
        for member in members:
            logging.info(f"Removing {member['userPrincipalName']} from AAD Guest RBAC Review")
            logging.info(requests.delete(url=f"https://graph.microsoft.com/v1.0/groups/c6f8666e-053a-4f09-a15c-6feee253af06/members/{member['id']}/$ref", headers=graph_api_headers).status_code)
    except Exception as e:
        logging.info(str(e))

    # getting subscriptions
    subscriptions = [ServiceBusMessage(f"{sub['displayName']},{sub['subscriptionId']}") for sub in requests.get(url="https://management.azure.com/subscriptions?api-version=2020-01-01", headers=rest_api_headers).json()["value"] if sub["displayName"] not in ["Access to Azure Active Directory", "BITM", "Free Trial"]]
    logging.info("-------------------------------------------------------------------------------------")
    logging.info(f"******* Completed getting subscriptions *******")

    # sending subscription names to the servicebus queue
    try:
        with ServiceBusClient.from_connection_string(os.environ["SERVICE_BUS_CONNECTION_STR"]) as client:
            with client.get_queue_sender(queue_name=os.environ["SERVICE_BUS_QUEUE_NAME"]) as sender:
                sender.send_messages(subscriptions)
    except Exception as e:
        logging.info(str(e))
    logging.info("-------------------------------------------------------------------------------------")
    logging.info(f"******* Completed sending servicebus queue messages *******")

    # creating append block blob
    try:
        blob_service_client = BlobServiceClient.from_connection_string(os.environ["AZURERBAC_STORAGE_ACCOUNT_CONNECTION_STRING"])
        blob_client = blob_service_client.get_blob_client("rbacreport", "rbac_report.csv")
        blob_client.create_append_blob()
    except Exception as e:
        logging.info(str(e))
    logging.info("-------------------------------------------------------------------------------------")
    logging.info(f"******* Completed creating append blob *******")