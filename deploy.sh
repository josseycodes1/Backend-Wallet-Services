# deploy.sh
#!/bin/bash

echo "=== Preparing Django App for Leapcell ==="

# Check if all required files exist
echo "Checking required files..."
for file in "requirements.txt" "Procfile" "runtime.txt"; do
    if [ ! -f "$file" ]; then
        echo "Error: $file not found!"
        exit 1
    fi
done

echo "✓ All required files found"

# Install dependencies locally to check
echo "Installing dependencies..."
pip install -r requirements.txt

# Collect static files
echo "Collecting static files..."
python manage.py collectstatic --noinput

# Run migrations
echo "Running migrations..."
python manage.py migrate

# Create superuser if needed
# echo "Creating superuser..."
# python manage.py createsuperuser --noinput --email admin@example.com

echo "=== Deployment Preparation Complete ==="
echo ""
echo "To deploy to Leapcell:"
echo "1. Push your code to GitHub"
echo "2. Connect your repo to Leapcell"
echo "3. Set environment variables:"
echo "   - SECRET_KEY"
echo "   - DATABASE_URL"
echo "   - PAYSTACK_SECRET_KEY"
echo "   - GOOGLE_OAUTH_CLIENT_ID"
echo "   - SITE_URL (your Leapcell app URL)"
echo ""
echo "Your app will be available at: https://your-app.leapcell.dev"