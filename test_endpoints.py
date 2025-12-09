import requests
import json

BASE_URL = "http://127.0.0.1:8001"  # Use localhost for testing

def test_endpoints():
    print("Testing Wallet Service Endpoints...")
    
    # 1. Test health check
    print("\n1. Testing health check...")
    try:
        response = requests.get(f"{BASE_URL}/")
        print(f"   Status: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 2. Test Swagger
    print("\n2. Testing Swagger...")
    try:
        response = requests.get(f"{BASE_URL}/swagger/")
        print(f"   Status: {response.status_code}")
        print(f"   Swagger accessible: {'Yes' if response.status_code == 200 else 'No'}")
    except Exception as e:
        print(f"   Error: {e}")
    
    # 3. Test OpenAPI schema
    print("\n3. Testing OpenAPI schema...")
    try:
        response = requests.get(f"{BASE_URL}/swagger/?format=openapi")
        print(f"   Status: {response.status_code}")
        if response.status_code == 200:
            print("   Schema generation: SUCCESS")
        else:
            print(f"   Schema error: {response.text[:200]}")
    except Exception as e:
        print(f"   Error: {e}")
    
    print("\nTesting complete!")

if __name__ == "__main__":
    test_endpoints()