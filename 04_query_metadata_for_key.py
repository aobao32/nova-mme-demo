#!/usr/bin/env python3
"""Query S3 Vector Bucket to find key by metadata path"""

import boto3
import json
import sys
from typing import List, Dict, Any

# AWS clients
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
VECTOR_BUCKET = 'my-nova-mme-demo-01'
INDEX_NAME = 'my-image-index-01'
MODEL_ID = 'amazon.nova-2-multimodal-embeddings-v1:0'
EMBEDDING_DIMENSION = 3072
SEARCH_PATH = 'test-image/01/b-00.jpg'  # Default value

def generate_text_embedding(text: str) -> List[float]:
    """Generate embedding for text using Nova MME"""
    print(f"\nGenerating query embedding...")
    
    # Prepare model input for text embedding
    # Use GENERIC_RETRIEVAL to match GENERIC_INDEX used during indexing
    model_input = {
        "taskType": "SINGLE_EMBEDDING",
        "singleEmbeddingParams": {
            "embeddingPurpose": "GENERIC_RETRIEVAL",
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

def query_by_metadata(
    vector_bucket: str, index_name: str, search_path: str
) -> List[Dict[str, Any]]:
    """Query vectors using metadata filter with query_vectors API"""
    print("=" * 60)
    print("Query Vector Key by Metadata")
    print("=" * 60)
    print(f"\n  Vector Bucket: {vector_bucket}")
    print(f"  Index Name: {index_name}")
    print(f"  Searching for path: {search_path}")
    
    try:
        # Generate a valid query embedding using text
        query_embedding = generate_text_embedding("metadata query")
        
        # Create metadata filter for full_path
        metadata_filter = {"full_path": {"$eq": search_path}}
        
        print(f"\n  Querying with metadata filter...")
        print(f"  Filter: {json.dumps(metadata_filter, indent=2)}")
        
        # Query vectors with metadata filter
        response = s3vectors_client.query_vectors(
            vectorBucketName=vector_bucket,
            indexName=index_name,
            queryVector={'float32': query_embedding},
            topK=10,
            filter=metadata_filter,
            returnDistance=True,
            returnMetadata=True
        )
        
        results = response.get('vectors', [])
        print(f"✓ Found {len(results)} matching vector(s)")
        
        return results
        
    except Exception as e:
        print(f"\n✗ Error: {e}")
        import traceback
        traceback.print_exc()
        return []

def display_results(results: List[Dict[str, Any]]):
    """Display query results"""
    print("\n" + "=" * 60)
    print("Results")
    print("=" * 60)
    
    if not results:
        print("\nNo matching vectors found.")
        return
    
    for idx, vector in enumerate(results, 1):
        print(f"\n--- Vector {idx} ---")
        
        # Display key
        key = vector.get('key', 'N/A')
        print(f"  Key: {key}")
        
        # Display distance
        distance = vector.get('distance')
        if distance is not None:
            print(f"  Distance: {distance}")
        
        # Display metadata
        metadata = vector.get('metadata', {})
        if metadata:
            print(f"  Metadata:")
            for meta_key, meta_value in metadata.items():
                print(f"    {meta_key}: {meta_value}")

def main():
    """Main function"""
    # Check if path is provided as command line argument
    if len(sys.argv) > 1:
        search_path = sys.argv[1]
    else:
        search_path = SEARCH_PATH
    
    # Query vectors by metadata
    results = query_by_metadata(
        vector_bucket=VECTOR_BUCKET,
        index_name=INDEX_NAME,
        search_path=search_path
    )
    
    # Display results
    display_results(results)
    
    print("\n" + "=" * 60)
    if results:
        print("✓ Query Completed Successfully!")
    else:
        print("No matching vectors found.")
    print("=" * 60)


if __name__ == '__main__':
    main()
