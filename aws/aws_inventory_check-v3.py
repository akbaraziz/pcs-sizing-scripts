#!/usr/bin/env python3

"""
This script is designed to automate tasks related to AWS management. It performs the following tasks:

1. Checks and installs necessary AWS packages (boto3).
2. Checks and installs necessary tools (awscli, kubectl).
3. Logs into AWS using AWS CLI.
4. Collects and prints inventory of AWS resources (EC2 Instances, VPCs, S3 Buckets, EKS Clusters).
5. Collects and prints data from specified EKS clusters (Pods, Nodes, Containers).
6. Writes the collected data to a CSV file.

Prerequisites:
1. You need to have Python 3 installed on your machine.
2. You need to have pip (Python package installer) installed.
3. You need to have 'awscli' and 'kubectl' installed, or permissions to install them.
4. You need to have access to an AWS account and the necessary permissions to view and manage resources.
5. You need to know the name of the EKS clusters you want to scan.
"""

import os
import subprocess
import sys
import csv
import boto3
from botocore.exceptions import NoCredentialsError, BotoCoreError

def check_aws_packages():
    try:
        import boto3
    except ImportError:
        print("boto3 is not installed. Installing...")
        try:
            subprocess.run('pip3 install boto3', shell=True, check=True)
        except subprocess.CalledProcessError as e:
            print(f"Error installing boto3: {e}")
            sys.exit(1)

check_aws_packages()

def check_tools():
    tools = {
        'aws': ['--version'], 
        'kubectl': ['version', '--client']
    }
    for tool, version_command in tools.items():
        try:
            subprocess.run([tool] + version_command, check=True)
            print(f"{tool} is installed correctly.")
        except FileNotFoundError:
            print(f"{tool} is not installed. Installing...")
            try:
                if tool == 'aws':
                    subprocess.run('pip3 uninstall -y awscli', shell=True, check=True)
                    subprocess.run('curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"', shell=True, check=True)
                    subprocess.run('unzip awscliv2.zip', shell=True, check=True)
                    subprocess.run('sudo ./aws/install', shell=True, check=True)
                elif tool == 'kubectl':
                    subprocess.run('sudo snap install kubectl --classic', shell=True, check=True)
            except subprocess.CalledProcessError as e:
                print(f"Error installing {tool}: {e}")
                sys.exit(1)

def login_aws():
    try:
        boto3.client('sts').get_caller_identity()
        print("Logged into AWS successfully.")
    except (NoCredentialsError, BotoCoreError) as e:
        print(f"Error logging into AWS: {e}")
        sys.exit(1)

def get_inventory():
    try:
        inventory = {}
        ec2 = boto3.client('ec2')
        s3 = boto3.client('s3')
        eks = boto3.client('eks')

        inventory['EC2 Instances'] = len(ec2.describe_instances()['Reservations'])
        inventory['VPCs'] = len(ec2.describe_vpcs()['Vpcs'])
        inventory['S3 Buckets'] = len(s3.list_buckets()['Buckets'])
        inventory['EKS Clusters'] = len(eks.list_clusters()['clusters'])

        return inventory
    except Exception as e:
        print(f"Error getting AWS inventory: {e}")
        sys.exit(1)
  
def get_eks_data():
    clusters_data = []
    try:
        eks = boto3.client('eks')
        clusters = eks.list_clusters()['clusters']

        for cluster_name in clusters:
            cmd = f'aws eks update-kubeconfig --region {eks.describe_cluster(name=cluster_name)["cluster"]["arn"].split(":")[3]} --name {cluster_name}'
            subprocess.run(cmd, shell=True, check=True)
            subprocess.run('kubectl config view --merge --flatten > kubeconfig.yaml', shell=True, check=True)
            os.environ["KUBECONFIG"] = os.getcwd() + "/kubeconfig.yaml"

            nodes = subprocess.check_output('kubectl get nodes --no-headers | wc -l', shell=True).decode().strip()
            pods = subprocess.check_output('kubectl get pods --all-namespaces --no-headers | wc -l', shell=True).decode().strip()
            containers = subprocess.check_output('kubectl get pods --all-namespaces -o jsonpath="{..status.containerStatuses[].name}" | tr " " "\n" | wc -l', shell=True).decode().strip()

            clusters_data.append({
                'Cluster Name': cluster_name,
                'Nodes': nodes,
                'Pods': pods,
                'Containers': containers,
            })

    except Exception as e:
        print(f"Error getting EKS data: {e}")
        sys.exit(1)
    
    return clusters_data

if __name__ == "__main__":
    check_tools()
    login_aws()
    inventory = get_inventory()
    eks_data = get_eks_data()

    with open('aws_inventory.csv', 'w', newline='') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=['Resource Type', 'Count'])
        writer.writeheader()
        for resource_type, count in inventory.items():
            writer.writerow({'Resource Type': resource_type, 'Count': count})
    
    with open('eks_data.csv', 'w', newline='') as csvfile:
        fieldnames = ['Cluster Name', 'Nodes', 'Pods', 'Containers']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for cluster_data in eks_data:
            writer.writerow(cluster_data)
