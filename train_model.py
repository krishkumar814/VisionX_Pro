from app import app
from services.ml_service import train_performance_model

if __name__ == "__main__":
    print("Bootstrapping Machine Learning Model for Student Performance...")
    with app.app_context():
        train_performance_model()
    print("Training Complete!")
