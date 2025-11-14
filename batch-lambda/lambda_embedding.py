"""
Lambda function to process SQS messages and generate embeddings
This function reads image info from SQS, generates embeddings using Nova MME,
and writes them to S3 Vector Bucket
"""

import json
import boto3
import base64
import uuid
from typing import Dict, Any

# AWS clients (initialized outside handler for reuse)
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
s3_client = boto3.client('s3', region_name='us-east-1')
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
MODEL_ID = 'amazon.nova-2-multimodal-embeddings-v1:0'
EMBEDDING_DIMENSION = 3072
VECTOR_BUCKET = 'my-nova-mme-demo-01'
INDEX_NAME = 'my-image-index-02-lambda'


def get_image_format(key: str) -> str:
    """Determine image format from file extension"""
    if key.lower().endswith('.png'):
        return 'png'
    elif key.lower().endswith('.gif'):
        return 'gif'
    elif key.lower().endswith('.webp'):
        return 'webp'
    return 'jpeg'


def generate_embedding(bucket: str, key: str) -> Dict[str, Any]:
    """Generate embedding for an image from S3"""
    print(f"Processing: s3://{bucket}/{key}")
    
    # Download image from S3
    response = s3_client.get_object(Bucket=bucket, Key=key)
    image_bytes = response['Body'].read()
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    # Prepare model input
    model_input = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": EMBEDDING_DIMENSION,
            "image": {
                "format": get_image_format(key),
                "source": {
                    "bytes": image_base64
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
    embedding = result.get('embeddings', [{}])[0].get('embedding', [])
    
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
        's3_uri': f's3://{source_bucket}/{source_key}'
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
