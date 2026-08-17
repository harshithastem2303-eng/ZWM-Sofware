from app.models import Category, TrainingJob
from app.extensions import db

MIN_THRESHOLD = 100  # Example target count

def check_dataset_readiness_and_trigger():
    categories = Category.query.all()
    ready = all(cat.validated_count >= MIN_THRESHOLD for cat in categories)
    
    if ready:
        new_job = TrainingJob(status='queued')
        db.session.add(new_job)
        db.session.commit()
        # Trigger async ML training worker here
        return True
    return False