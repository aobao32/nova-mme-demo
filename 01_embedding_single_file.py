#!/usr/bin/env python3
"""Embed a single local image file using Nova MME"""

import boto3
import json
import base64
import uuid
from pathlib import Path
from typing import Dict, Any

# AWS clients
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
MODEL_ID = 'amazon.nova-2-multimodal-embeddings-v1:0'
EMBEDDING_DIMENSION = 3072
IMAGE_PATH = 'test-image/01/b-00.jpg'
VECTOR_BUCKET = 'my-nova-mme-demo-01'
INDEX_NAME = 'my-image-index-01'

def get_image_format(file_path: str) -> str:
    """Determine image format from file extension"""
    if file_path.lower().endswith('.png'):
        return 'png'
    return 'jpeg'

def generate_embedding(image_path: str) -> Dict[str, Any]:
    """Generate embedding for a single local image file"""
    print(f"\nProcessing: {image_path}")
    
    # Read local image file
    path = Path(image_path)
    if not path.exists():
        raise FileNotFoundError(f"Image file not found: {image_path}")
    
    with open(path, 'rb') as f:
        image_bytes = f.read()
    
    image_base64 = base64.b64encode(image_bytes).decode('utf-8')
    
    # Prepare model input
    model_input = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_INDEX",
            "embeddingDimension": EMBEDDING_DIMENSION,
            "image": {
                "format": get_image_format(image_path),
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
        'image_path': image_path,
        'embedding': embedding,
        'dimension': len(embedding)
    }

def store_embedding_to_s3_vectors(
    embedding: list,
    image_path: str,
    vector_bucket: str,
    index_name: str
) -> Dict[str, Any]:
    """Store embedding vector to S3 Vectors with metadata"""
    # Generate unique ID using UUID directly (no prefix to avoid hotspot)
    vector_key = uuid.uuid4().hex
    
    # Prepare metadata
    path_obj = Path(image_path)
    metadata = {
        'file_path': str(path_obj.parent),
        'file_name': path_obj.name,
        'full_path': image_path
    }
    
    print(f"\nStoring to S3 Vectors...")
    print(f"  Vector Bucket: {vector_bucket}")
    print(f"  Index Name: {index_name}")
    print(f"  Vector Key: {vector_key}")
    
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
    
    print(f"✓ Stored to S3 Vectors!")
    print(f"\n  Vector Information:")
    print(f"    Vector Key: {vector_key}")
    print(f"    Embedding Dimension: {len(embedding)}")
    print(f"    Vector Bucket: {vector_bucket}")
    print(f"    Index Name: {index_name}")
    print(f"\n  Metadata:")
    for key, value in metadata.items():
        print(f"    {key}: {value}")
    print(f"\n  API Response:")
    print(f"    {json.dumps(response, indent=2, default=str)}")
    
    return {
        'vector_key': vector_key,
        'vector_bucket': vector_bucket,
        'index_name': index_name,
        'metadata': metadata,
        'response': response
    }

def main():
    """Main function to generate embedding for single image"""
    print("=" * 60)
    print("Nova MME Single Image Embedding")
    print("=" * 60)
    
    try:
        # Generate embedding
        result = generate_embedding(IMAGE_PATH)
        
        print(f"✓ Embedding generated!")
        print(f"  Image: {result['image_path']}")
        print(f"  Dimension: {result['dimension']}")
        print(f"  First 5 values: {result['embedding'][:5]}")
        print(f"  Last 5 values: {result['embedding'][-5:]}")
        
        # Store to S3 Vectors
        store_result = store_embedding_to_s3_vectors(
            embedding=result['embedding'],
            image_path=result['image_path'],
            vector_bucket=VECTOR_BUCKET,
            index_name=INDEX_NAME
        )
        
        print("\n" + "=" * 60)
        print("✓ Embedding Process Completed Successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"✗ Error: {e}")

if __name__ == '__main__':
    main()