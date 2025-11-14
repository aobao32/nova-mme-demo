"""
Lambda function to process SQS messages and generate embeddings
This function reads image info from SQS, generates embeddings using Twelve Labs Marengo Embed 3.0,
and writes them to S3 Vector Bucket
"""

import json
import boto3
import uuid
from typing import Dict, Any

# AWS clients (initialized outside handler for reuse)
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
s3_client = boto3.client('s3', region_name='us-east-1')
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
MODEL_ID = 'twelvelabs.marengo-embed-3-0-v1:0'
EMBEDDING_DIMENSION = 512  # TME3 uses 512 dimensions (reduced from 1024)
VECTOR_BUCKET = 'my-nova-mme-demo-01'
INDEX_NAME = 'my-image-index-03-tme3'


def get_account_id() -> str:
    """Get AWS account ID"""
    sts_client = boto3.client('sts', region_name='us-east-1')
    return sts_client.get_caller_identity()['Account']


def generate_embedding(bucket: str, key: str) -> Dict[str, Any]:
    """Generate embedding for an image from S3 using Twelve Labs Marengo Embed 3.0"""
    print(f"Processing: s3://{bucket}/{key}")
    
    # Get AWS account ID for bucketOwner
    account_id = get_account_id()
    
    # Prepare model input for TME3
    # Using S3 location directly (no need to download and base64 encode)
    model_input = {
        "inputType": "image",
        "image": {
            "mediaSource": {
                "s3Location": {
                    "uri": f"s3://{bucket}/{key}",
                    "bucketOwner": account_id
                }
            }
        }
    }
    
    # Invoke Bedrock model synchronously
    response = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(model_input)
    )
    
    # Parse response
    result = json.loads(response['body'].read())
    
    # TME3 response format: dict with 'data' key containing a list with embedding
    if isinstance(result, dict) and 'data' in result:
        data_list = result['data']
        if isinstance(data_list, list) and len(data_list) > 0:
            first_item = data_list[0]
            if isinstance(first_item, dict) and 'embedding' in first_item:
                embedding = first_item['embedding']
            else:
                raise ValueError(f"Unexpected data item format: {first_item}")
        else:
            raise ValueError(f"Empty data list in response")
    elif isinstance(result, dict) and 'embedding' in result:
        # Alternative format: dict with 'embedding' key
        embedding_list = result['embedding']
        if isinstance(embedding_list, list) and len(embedding_list) > 0:
            first_item = embedding_list[0]
            if isinstance(first_item, dict) and 'embedding' in first_item:
                embedding = first_item['embedding']
            elif isinstance(first_item, (int, float)):
                embedding = embedding_list
            else:
                raise ValueError(f"Unexpected embedding item format: {first_item}")
        else:
            embedding = embedding_list
    else:
        raise ValueError(f"Unexpected response format: {result}")
    
    return {
        'bucket': bucket,
        'key': key,
        'embedding': embedding,
        'dimension': len(embedding)
    }


def store_embedding_to_s3_vectors(
    embedding: list,
    source_bucket: str,
    source_key: str,
    vector_bucket: str,
    index_name: str
) -> Dict[str, Any]:
    """Store embedding vector to S3 Vectors with metadata"""
    # Generate unique ID using UUID directly (no prefix to avoid hotspot)
    vector_key = uuid.uuid4().hex
    
    # Prepare metadata
    metadata = {
        'source_bucket': source_bucket,
        'source_key': source_key,
        's3_uri': f's3://{source_bucket}/{source_key}',
        'model': 'twelvelabs-marengo-embed-3-0'
    }
    
    print(f"Storing to S3 Vectors with key: {vector_key}")
    
    # Write embedding to S3 Vectors using put_vectors API
    response = s3vectors_client.put_vectors(
        vectorBucketName=vector_bucket,
        indexName=index_name,
        vectors=[
            {
                'key': vector_key,
                'data': {'float32': embedding},
                'metadata': metadata
            }
        ]
    )
    
    return {
        'vector_key': vector_key,
        'vector_bucket': vector_bucket,
        'index_name': index_name,
        'metadata': metadata,
        'response': response
    }


def process_message(message_body: Dict) -> Dict[str, Any]:
    """Process a single SQS message"""
    bucket = message_body['bucket']
    key = message_body['key']
    
    try:
        # Generate embedding
        embedding_result = generate_embedding(bucket, key)
        print(f"✓ Embedding generated (dimension: {embedding_result['dimension']})")
        
        # Store to S3 Vectors
        store_result = store_embedding_to_s3_vectors(
            embedding=embedding_result['embedding'],
            source_bucket=bucket,
            source_key=key,
            vector_bucket=VECTOR_BUCKET,
            index_name=INDEX_NAME
        )
        print(f"✓ Stored to S3 Vectors")
        
        return {
            'status': 'success',
            'source': f's3://{bucket}/{key}',
            'vector_key': store_result['vector_key']
        }
    
    except Exception as e:
        print(f"✗ Error processing {key}: {e}")
        return {
            'status': 'error',
            'source': f's3://{bucket}/{key}',
            'error': str(e)
        }


def lambda_handler(event, context):
    """
    Lambda handler function
    Processes SQS messages containing S3 image information
    """
    print(f"Received {len(event['Records'])} messages")
    
    results = []
    
    # Process each SQS message
    for record in event['Records']:
        try:
            # Parse message body
            message_body = json.loads(record['body'])
            
            # Process the message
            result = process_message(message_body)
            results.append(result)
        
        except Exception as e:
            print(f"✗ Error processing record: {e}")
            results.append({
                'status': 'error',
                'error': str(e)
            })
    
    # Summary
    success_count = sum(1 for r in results if r['status'] == 'success')
    error_count = sum(1 for r in results if r['status'] == 'error')
    
    print(f"\nSummary: {success_count} succeeded, {error_count} failed")
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'processed': len(results),
            'succeeded': success_count,
            'failed': error_count,
            'results': results
        })
    }
