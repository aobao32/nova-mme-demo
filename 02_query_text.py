#!/usr/bin/env python3
"""Query S3 Vector Bucket using text with Nova MME"""

import boto3
import json
from typing import Dict, Any, List

# AWS clients
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
MODEL_ID = 'amazon.nova-2-multimodal-embeddings-v1:0'
EMBEDDING_DIMENSION = 3072
VECTOR_BUCKET = 'my-nova-mme-demo-01'
#INDEX_NAME = 'my-image-index-01'
INDEX_NAME = 'my-image-index-02-lambda'
QUERY_TEXT = 'Wind turbine'
TOP_K = 5  # Number of results to return

def generate_text_embedding(text: str) -> List[float]:
    """Generate embedding for text using Nova MME"""
    print(f"\nGenerating embedding for text: '{text}'")
    
    # Prepare model input for text embedding
    # Use IMAGE_RETRIEVAL to match IMAGE_INDEX used during indexing
    model_input = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "IMAGE_RETRIEVAL",
            "embeddingDimension": EMBEDDING_DIMENSION,
            "text": {
                "truncationMode": "END",
                "value": text
            }
        }
    }
    
    # Invoke Bedrock model
    response = bedrock_client.invoke_model(
        modelId=MODEL_ID,
        body=json.dumps(model_input)
    )
    
    # Parse response
    result = json.loads(response['body'].read())
    embedding = result.get('embeddings', [{}])[0].get('embedding', [])
    
    print(f"✓ Embedding generated (dimension: {len(embedding)})")
    
    return embedding

def query_vectors(
    query_embedding: List[float],
    vector_bucket: str,
    index_name: str,
    top_k: int = 3
) -> List[Dict[str, Any]]:
    """Query S3 Vectors for similar vectors"""
    print(f"\nQuerying S3 Vectors...")
    print(f"  Vector Bucket: {vector_bucket}")
    print(f"  Index Name: {index_name}")
    print(f"  Top K: {top_k}")
    
    # Query vectors using query_vectors API
    response = s3vectors_client.query_vectors(
        vectorBucketName=vector_bucket,
        indexName=index_name,
        queryVector={'float32': query_embedding},
        topK=top_k,
        returnDistance=True,
        returnMetadata=True
    )
    
    # Extract results from response (field name is 'vectors', not 'results')
    results = response.get('vectors', [])
    print(f"✓ Found {len(results)} results")
    
    return results

def display_results(results: List[Dict[str, Any]]):
    """Display query results in a formatted way"""
    print("\n" + "=" * 60)
    print("Query Results")
    print("=" * 60)
    
    if not results:
        print("\nNo results found.")
        return
    
    for idx, result in enumerate(results, 1):
        print(f"\n--- Result {idx} ---")
        
        # Extract key
        key = result.get('key', 'N/A')
        print(f"  Key: {key}")
        
        # Extract distance/score
        distance = result.get('distance')
        if distance is not None:
            print(f"  Distance: {distance}")
        
        score = result.get('score')
        if score is not None:
            print(f"  Score: {score}")
        
        # Extract metadata
        metadata = result.get('metadata', {})
        if metadata:
            print(f"  Metadata:")
            
            # Display full path
            full_path = metadata.get('full_path')
            if full_path:
                print(f"    Full Path: {full_path}")
            
            # Display file name
            file_name = metadata.get('file_name')
            if file_name:
                print(f"    File Name: {file_name}")
            
            # Display file path
            file_path = metadata.get('file_path')
            if file_path:
                print(f"    File Path: {file_path}")
            
            # Display any other metadata
            for key, value in metadata.items():
                if key not in ['full_path', 'file_name', 'file_path']:
                    print(f"    {key}: {value}")


def main():
    """Main function to query vectors using text"""
    print("=" * 60)
    print("Nova MME Text-to-Image Query")
    print("=" * 60)
    
    try:
        # Generate embedding for query text
        query_embedding = generate_text_embedding(QUERY_TEXT)
        
        # Query S3 Vectors
        results = query_vectors(
            query_embedding=query_embedding,
            vector_bucket=VECTOR_BUCKET,
            index_name=INDEX_NAME,
            top_k=TOP_K
        )
        
        # Display results
        display_results(results)
        
        print("\n" + "=" * 60)
        print("✓ Query Completed Successfully!")
        print("=" * 60)
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    main()