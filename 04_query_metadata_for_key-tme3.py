#!/usr/bin/env python3
"""Query S3 Vector Bucket to find key by metadata path using TME3"""

import boto3
import json
import sys
from typing import List, Dict, Any

# AWS clients
bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
VECTOR_BUCKET = 'my-nova-mme-demo-01'
INDEX_NAME = 'my-image-index-03-tme3'
MODEL_ID = 'twelvelabs.marengo-embed-3-0-v1:0'
EMBEDDING_DIMENSION = 512
SEARCH_S3_URI = 's3://nova-mme-demo-source-image/01/b-01.jpg'  # Default value

def generate_text_embedding(text: str) -> List[float]:
    """Generate embedding for text using Twelve Labs Marengo Embed 3.0"""
    print(f"\nGenerating query embedding...")
    
    # Prepare model input for TME3 text embedding
    model_input = {
        "inputType": "text",
        "text": {
            "inputText": text
        }
    }
    
    # Invoke Bedrock model
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
    
    print(f"✓ Embedding generated (dimension: {len(embedding)})")
    
    return embedding

def query_by_metadata(
    vector_bucket: str, index_name: str, search_s3_uri: str
) -> List[Dict[str, Any]]:
    """Query vectors using metadata filter with query_vectors API"""
    print("=" * 60)
    print("Query Vector Key by Metadata (TME3)")
    print("=" * 60)
    print(f"\n  Vector Bucket: {vector_bucket}")
    print(f"  Index Name: {index_name}")
    print(f"  Searching for S3 URI: {search_s3_uri}")
    
    try:
        # Generate a valid query embedding using text
        query_embedding = generate_text_embedding("metadata query")
        
        # Create metadata filter for s3_uri
        metadata_filter = {"s3_uri": {"$eq": search_s3_uri}}
        
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
    # Check if S3 URI is provided as command line argument
    if len(sys.argv) > 1:
        search_s3_uri = sys.argv[1]
    else:
        search_s3_uri = SEARCH_S3_URI
    
    # Query vectors by metadata
    results = query_by_metadata(
        vector_bucket=VECTOR_BUCKET,
        index_name=INDEX_NAME,
        search_s3_uri=search_s3_uri
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
