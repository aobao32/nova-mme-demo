#!/usr/bin/env python3
"""Test script to send a single message to SQS FIFO queue"""

import boto3
import json
import sys
from datetime import datetime

# AWS clients
sqs_client = boto3.client('sqs', region_name='us-east-1')

# Configuration
SQS_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/133129065110/embedding-queue-tme3.fifo'

# Test image S3 URI
TEST_S3_URI = 's3://nova-mme-demo-source-image/01/b-01.jpg'


def parse_s3_uri(s3_uri: str) -> dict:
    """Parse S3 URI into bucket and key"""
    if not s3_uri.startswith('s3://'):
        raise ValueError(f"Invalid S3 URI: {s3_uri}")
    
    # Remove s3:// prefix
    path = s3_uri[5:]
    
    # Split into bucket and key
    parts = path.split('/', 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid S3 URI format: {s3_uri}")
    
    bucket = parts[0]
    key = parts[1]
    
    return {
        'bucket': bucket,
        'key': key
    }


def send_test_message(s3_uri: str, queue_url: str):
    """Send a test message to SQS FIFO queue"""
    print("=" * 60)
    print("Send Test Message to SQS")
    print("=" * 60)
    
    # Parse S3 URI
    try:
        s3_info = parse_s3_uri(s3_uri)
        print(f"\nParsed S3 URI:")
        print(f"  Bucket: {s3_info['bucket']}")
        print(f"  Key: {s3_info['key']}")
    except ValueError as e:
        print(f"\n✗ Error: {e}")
        return
    
    # Prepare message body (same format as list_bucket_sqs.py)
    message_body = {
        'bucket': s3_info['bucket'],
        'key': s3_info['key'],
        'size': 0,  # Unknown size for test
        'last_modified': datetime.now().isoformat()
    }
    
    print(f"\nMessage body:")
    print(json.dumps(message_body, indent=2))
    
    # Send message to SQS
    try:
        print(f"\nSending message to SQS...")
        
        response = sqs_client.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageGroupId='embedding-group',
            # Use key as deduplication ID
            MessageDeduplicationId=s3_info['key'].replace('/', '-')
        )
        
        print(f"✓ Message sent successfully!")
        print(f"\n  Message ID: {response['MessageId']}")
        print(f"  Sequence Number: {response.get('SequenceNumber', 'N/A')}")
        
        print("\n" + "=" * 60)
        print("Next Steps:")
        print("=" * 60)
        print("1. Check SQS queue in AWS Console")
        print("2. Monitor Lambda function logs in CloudWatch")
        print("3. Verify embedding is written to S3 Vector Bucket")
        print("\nTo check Lambda logs:")
        print("  aws logs tail /aws/lambda/embedding-nova-mme --follow --region us-east-1")
        
    except Exception as e:
        print(f"\n✗ Error sending message: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Main function"""
    # Check if S3 URI is provided as command line argument
    if len(sys.argv) > 1:
        s3_uri = sys.argv[1]
    else:
        s3_uri = TEST_S3_URI
    
    send_test_message(s3_uri, SQS_QUEUE_URL)


if __name__ == '__main__':
    main()
