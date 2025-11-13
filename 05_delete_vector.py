#!/usr/bin/env python3
"""Delete a vector from S3 Vector Bucket"""

import boto3
import json
import sys
from typing import Dict, Any

# AWS clients
s3vectors_client = boto3.client('s3vectors', region_name='us-east-1')

# Configuration
VECTOR_BUCKET = 'my-nova-mme-demo-01'
INDEX_NAME = 'my-image-index-01'
VECTOR_KEY = 'b3014d28baba40bfb4651c123f43f0c7'  # Set this to the key you want to delete

def delete_vector(
    vector_bucket: str,
    index_name: str,
    vector_key: str
) -> Dict[str, Any]:
    """Delete a vector from S3 Vectors"""
    print("=" * 60)
    print("Delete Vector from S3 Vectors")
    print("=" * 60)
    print(f"\n  Vector Bucket: {vector_bucket}")
    print(f"  Index Name: {index_name}")
    print(f"  Vector Key: {vector_key}")
    
    try:
        # Delete vector using delete_vectors API
        response = s3vectors_client.delete_vectors(
            vectorBucketName=vector_bucket,
            indexName=index_name,
            keys=[vector_key]
        )
        
        print(f"\n✓ Vector deleted successfully!")
        print(f"\n  API Response:")
        print(f"    {json.dumps(response, indent=2, default=str)}")
        
        return {
            'success': True,
            'vector_key': vector_key,
            'response': response
        }
        
    except Exception as e:
        print(f"\n✗ Error deleting vector: {e}")
        return {
            'success': False,
            'vector_key': vector_key,
            'error': str(e)
        }

def main():
    """Main function to delete vector"""
    # Check if vector key is provided
    if len(sys.argv) > 1:
        vector_key = sys.argv[1]
    elif VECTOR_KEY:
        vector_key = VECTOR_KEY
    else:
        print("Error: No vector key provided!")
        print("\nUsage:")
        print(f"  python {sys.argv[0]} <vector_key>")
        print(f"  Or set VECTOR_KEY in the script")
        sys.exit(1)
    
    # Delete the vector
    result = delete_vector(
        vector_bucket=VECTOR_BUCKET,
        index_name=INDEX_NAME,
        vector_key=vector_key
    )
    
    print("\n" + "=" * 60)
    if result['success']:
        print("✓ Deletion Completed Successfully!")
    else:
        print("✗ Deletion Failed!")
    print("=" * 60)

if __name__ == '__main__':
    main()