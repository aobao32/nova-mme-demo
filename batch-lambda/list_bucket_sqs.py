#!/usr/bin/env python3
"""List images from S3 bucket and send to SQS FIFO queue for processing"""

import boto3
import json
import os
from typing import List, Dict, Set

# AWS clients
s3_client = boto3.client('s3', region_name='us-east-1')
sqs_client = boto3.client('sqs', region_name='us-east-1')

# Configuration
SOURCE_BUCKET = 'nova-mme-demo-source-image'
SQS_QUEUE_URL = 'https://sqs.us-east-1.amazonaws.com/133129065110/embedding-queue.fifo'
IMAGE_EXTENSIONS = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
BATCH_SIZE = 10  # Number of messages to send in one batch
PROGRESS_FILE = 'embedding_progress.json'  # Local progress tracking file

def list_images_from_s3(bucket: str, prefix: str = '') -> List[Dict]:
    """List all image files from S3 bucket"""
    print(f"Listing images from s3://{bucket}/{prefix}...")
    
    image_files = []
    paginator = s3_client.get_paginator('list_objects_v2')
    
    for page in paginator.paginate(Bucket=bucket, Prefix=prefix):
        if 'Contents' not in page:
            continue
        
        for obj in page['Contents']:
            key = obj['Key']
            # Check if file is an image
            if key.lower().endswith(IMAGE_EXTENSIONS):
                image_files.append({
                    'bucket': bucket,
                    'key': key,
                    'size': obj['Size'],
                    'last_modified': obj['LastModified'].isoformat()
                })
    
    print(f"✓ Found {len(image_files)} image files")
    return image_files

def send_to_sqs_batch(messages: List[Dict], queue_url: str) -> Dict:
    """Send messages to SQS FIFO queue in batch"""
    entries = []
    
    for idx, message in enumerate(messages):
        # Create message entry
        entry = {
            'Id': str(idx),
            'MessageBody': json.dumps(message),
            'MessageGroupId': 'embedding-group',
            # Use S3 key as deduplication ID to avoid duplicates
            'MessageDeduplicationId': message['key'].replace('/', '-')
        }
        entries.append(entry)
    
    # Send batch
    response = sqs_client.send_message_batch(
        QueueUrl=queue_url,
        Entries=entries
    )
    
    return response

def load_progress() -> Set[str]:
    """Load progress from local file"""
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, 'r') as f:
                data = json.load(f)
                return set(data.get('processed_keys', []))
        except Exception as e:
            print(f"Warning: Could not load progress file: {e}")
    return set()

def save_progress(processed_keys: Set[str]):
    """Save progress to local file"""
    try:
        with open(PROGRESS_FILE, 'w') as f:
            json.dump({
                'processed_keys': list(processed_keys),
                'total_processed': len(processed_keys)
            }, f, indent=2)
    except Exception as e:
        print(f"Warning: Could not save progress file: {e}")

def send_images_to_sqs(image_files: List[Dict], queue_url: str, processed_keys: Set[str]):
    """Send all image files to SQS queue in batches, skipping already processed"""
    # Filter out already processed files
    pending_files = [f for f in image_files if f['key'] not in processed_keys]
    
    if not pending_files:
        print("\n✓ All files have already been sent to SQS")
        return
    
    print(f"\nTotal files: {len(image_files)}")
    print(f"Already processed: {len(processed_keys)}")
    print(f"Pending to send: {len(pending_files)}")
    print(f"\nSending {len(pending_files)} messages to SQS...")
    
    total_sent = 0
    failed = 0
    newly_processed = set()
    
    # Process in batches (SQS batch limit is 10)
    for i in range(0, len(pending_files), BATCH_SIZE):
        batch = pending_files[i:i + BATCH_SIZE]
        
        try:
            response = send_to_sqs_batch(batch, queue_url)
            
            # Check for successful and failed messages
            successful = len(response.get('Successful', []))
            failed_batch = len(response.get('Failed', []))
            
            total_sent += successful
            failed += failed_batch
            
            # Track successfully sent files
            if successful > 0:
                for idx, msg in enumerate(response.get('Successful', [])):
                    msg_id = int(msg['Id'])
                    newly_processed.add(batch[msg_id]['key'])
            
            if failed_batch > 0:
                print(f"  Batch {i//BATCH_SIZE + 1}: {successful} sent, {failed_batch} failed")
                for failure in response.get('Failed', []):
                    print(f"    Failed: {failure}")
            else:
                print(f"  Batch {i//BATCH_SIZE + 1}: {successful} messages sent")
            
            # Save progress after each batch
            if newly_processed:
                save_progress(processed_keys | newly_processed)
        
        except Exception as e:
            print(f"  ✗ Error sending batch {i//BATCH_SIZE + 1}: {e}")
            failed += len(batch)
    
    print(f"\n✓ Summary:")
    print(f"  Total sent: {total_sent}")
    print(f"  Failed: {failed}")
    if len(pending_files) > 0:
        print(f"  Success rate: {total_sent / len(pending_files) * 100:.1f}%")

def main():
    """Main function"""
    print("=" * 60)
    print("List S3 Images and Send to SQS")
    print("=" * 60)
    
    try:
        # Load progress from previous runs
        processed_keys = load_progress()
        if processed_keys:
            print(f"\n✓ Loaded progress: {len(processed_keys)} files already processed")
        
        # List all images from S3
        image_files = list_images_from_s3(SOURCE_BUCKET)
        
        if not image_files:
            print("No image files found in bucket")
            return
        
        # Send to SQS queue (skipping already processed)
        send_images_to_sqs(image_files, SQS_QUEUE_URL, processed_keys)
        
        print("\n" + "=" * 60)
        print("✓ Process Completed!")
        print(f"Progress saved to: {PROGRESS_FILE}")
        print("=" * 60)
    
    except KeyboardInterrupt:
        print("\n\n✗ Process interrupted by user")
        print(f"Progress has been saved to: {PROGRESS_FILE}")
        print("You can safely re-run this script to continue")
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()