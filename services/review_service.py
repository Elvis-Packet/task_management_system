from datetime import datetime

from extensions import db

from models.enums import (
    VerificationStatus,
    FinalStatus
)



def review_activity(

        activity,

        manager,

        verification,

        quality,

        timeliness,

        comments

):


    activity.reviewed_by = manager.id


    activity.reviewed_at=datetime.utcnow()


    activity.verification_status=verification



    activity.quality_rating=int(
        quality
    )


    activity.timeliness_rating=int(
        timeliness
    )



    activity.activity_score=round(

        (
            activity.quality_rating
            +
            activity.timeliness_rating

        ) / 2,

        2

    )



    activity.manager_comments=comments



    if verification == VerificationStatus.VERIFIED:


        activity.final_status = (
            FinalStatus.SUCCESSFUL
        )


    elif verification == VerificationStatus.REJECTED:


        activity.final_status = (
            FinalStatus.UNSUCCESSFUL
        )


    db.session.commit()

    from services.performance_summary_service import (
        calculate_summary
    )


    calculate_summary(
        activity.plan.employee
    )
    return True
