#!/usr/bin/env python3

"""
This script is designed to automate tasks related to Azure management. It performs the following tasks:

1. Checks and installs necessary Azure packages (azure-identity, azure-mgmt-resource, azure-mgmt-compute,
   azure-mgmt-network, azure-mgmt-storage, azure-mgmt-containerservice).
2. Checks and installs necessary tools (az, kubectl).
3. Logs into Azure using InteractiveBrowserCredential.
4. Collects and prints inventory of Azure resources (VMs, Networks, Storage Accounts, AKS Clusters).
5. Collects and prints data from specified AKS clusters (Pods, Nodes, Containers).
6. Writes the collected data to a CSV file.


Prerequisites:
1. You need to have Python 3 installed on your machine.
2. You need to have pip (Python package installer) installed.
3. You need to have 'az' (Azure CLI) and 'kubectl' installed, or permissions to install them.
4. You need to have access to an Azure subscription and the necessary permissions to view and manage resources.
5. You need to know the name and resource group of the AKS clusters you want to scan.

"""

import os
import subprocess
import sys
import re
import csv
import getpass
from azure.identity import InteractiveBrowserCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.compute import ComputeManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.storage import StorageManagementClient
from azure.mgmt.containerservice import ContainerServiceClient


# Check if azure and azure-mgmt is installed
def check_azure_packages():
    try:
        import azure.mgmt.compute
        import azure
    except ImportError:
        print("azure or azure-mgmt is not installed. Installing...")
        try:
            subprocess.run('pip3 install azure-identity azure-mgmt-resource azure-mgmt-compute azure-mgmt-network azure-mgmt-storage azure-mgmt-containerservice', shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error installing azure, azure-mgmt or azure-identity: {e}")
            sys.exit(1)

# Call the function to check and install azure packages
check_azure_packages()


# Check if the required tools are installed
def check_tools():
    tools = {
        'az': ['--version'], 
        'kubectl': ['version', '--client']
    }
    for tool, version_command in tools.items():
        try:
            subprocess.run([tool] + version_command, check=True, stdout=subprocess.PIPE)
        except FileNotFoundError:
            print(f"{tool} is not installed. Installing...")
            try:
                if tool == 'az':
                    subprocess.run('curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash', shell=True, check=True)
                elif tool == 'kubectl':
                    subprocess.run('sudo snap install kubectl --classic', shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error installing {tool}: {e}")
                sys.exit(1)


def login_azure():
    print("Please enter your Azure subscription ID:")
    subscription_id = input().strip()

    # Optional: validate subscription ID
    if not re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', subscription_id, re.I):
        print("Invalid subscription ID.")
        sys.exit(1)
        
    try:
        credential = InteractiveBrowserCredential()
    except Exception as e:
        print(f"Error logging into Azure: {e}")
        sys.exit(1)
    return credential, subscription_id


# Get Azure inventory
from azure.core.exceptions import HttpResponseError

def get_inventory(credential, subscription_id):
    try:
        inventory = {}
        resource_client = ResourceManagementClient(credential, subscription_id)
        compute_client = ComputeManagementClient(credential, subscription_id)
        network_client = NetworkManagementClient(credential, subscription_id)
        storage_client = StorageManagementClient(credential, subscription_id)
        containerservice_client = ContainerServiceClient(credential, subscription_id)

        inventory['VMs'] = len(list(compute_client.virtual_machines.list_all()))
        inventory['Networks'] = len(list(network_client.virtual_networks.list_all()))
        inventory['Storage Accounts'] = len(list(storage_client.storage_accounts.list()))
        inventory['AKS Clusters'] = len(list(containerservice_client.managed_clusters.list()))

        return inventory
    except Exception as e:
        print(f"Error getting Azure inventory: {e}")
        sys.exit(1)
  
def get_aks_data(credential, subscription_id):
    clusters_data = []  # List to store data of all clusters
    try:
        containerservice_client = ContainerServiceClient(credential, subscription_id)
        clusters = [c.name for c in containerservice_client.managed_clusters.list()]

        while True:
            print("Enter the name of the AKS cluster you want to scan, or 'done' to finish:")
            cluster_name = input().strip()
            if cluster_name.lower() == 'done':
                break
            elif cluster_name in clusters:
                print("Enter the Resource Group of the AKS cluster:")
                resource_group = input().strip()
                print(f"Getting data for {cluster_name}...")
                cmd = f'az aks get-credentials --resource-group {resource_group} --name {cluster_name}'
                result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                if result.returncode != 0:
                    print(f"Error running '{cmd}'. Please check the resource group and cluster name.\nError details: {result.stderr.decode()}")
                else:
                    subprocess.run('kubectl config view --merge --flatten', shell=True, check=True)
                    subprocess.run('kubectl get pods --all-namespaces', shell=True, check=True)

                    # count nodes
                    cmd = 'kubectl get nodes --no-headers | wc -l'
                    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    nodes = result.stdout.decode().strip()

                    # count pods
                    cmd = 'kubectl get pods --all-namespaces --no-headers | wc -l'
                    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    pods = result.stdout.decode().strip()

                    # count containers
                    cmd = 'kubectl get pods --all-namespaces -o jsonpath="{..status.containerStatuses[].name}" | tr " " "\n" | wc -l'
                    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
                    containers = result.stdout.decode().strip()

                    # Add cluster data to the list
                    clusters_data.append({
                        'Cluster Name': cluster_name,
                        'Nodes': nodes,
                        'Pods': pods,
                        'Containers': containers,
                    })

            else:
                print("Invalid cluster name. Please try again.")
    except Exception as e:
        print(f"Error getting AKS data: {e}")
        sys.exit(1)
    
    return clusters_data  # Return list of cluster data

if __name__ == "__main__":
    check_tools()
    credential, subscription_id = login_azure()
    inventory = get_inventory(credential, subscription_id)
    aks_data = get_aks_data(credential, subscription_id)

    # Write inventory to CSV
    with open('azure_inventory.csv', 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['Resource Type', 'Count'])
        writer.writeheader()
        for resource_type, count in inventory.items():
            writer.writerow({'Resource Type': resource_type, 'Count': count})
    
    # Write AKS data to CSV
    with open('aks_data.csv', 'w', newline='') as csvfile:
        fieldnames = ['Cluster Name', 'Nodes', 'Pods', 'Containers']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for cluster_data in aks_data:
            writer.writerow(cluster_data)