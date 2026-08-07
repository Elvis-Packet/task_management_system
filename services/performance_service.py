from models.activity import Activity
from models.performance import Performance
from models.enums import VerificationStatus

from extensions import db

from sqlalchemy import func



def calculate_activity_percentage(activity):


    if activity.activity_score == 0:

        return 0


    return round(

        (activity.activity_score / 5) * 100,

        2

    )




def calculate_employee_performance(

        employee_id,

        period_type

):


    activities = Activity.query.filter(

        Activity.plan.has(

            employee_id=employee_id

        ),

        Activity.verification_status == VerificationStatus.VERIFIED

    ).all()



    if not activities:

        return 0



    total = 0



    for activity in activities:


        total += calculate_activity_percentage(
            activity
        )



    return round(

        total / len(activities),

        2

    )
