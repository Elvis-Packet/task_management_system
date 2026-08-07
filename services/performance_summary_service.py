from extensions import db

from models.performance_summary import PerformanceSummary

from models.performance import Performance

from models.assigned_task_performance import AssignedTaskPerformance



def get_or_create_summary(employee):


    summary = PerformanceSummary.query.filter_by(

        employee_id=employee.id

    ).first()


    if summary:

        return summary



    summary=PerformanceSummary(

        employee_id=employee.id,

        employee_number=employee.employee_number

    )


    db.session.add(summary)

    db.session.commit()


    return summary



def calculate_summary(employee):


    summary=get_or_create_summary(employee)



    normal = Performance.query.filter_by(

        employee_id=employee.id

    ).order_by(

        Performance.created_at.desc()

    ).first()



    assigned = AssignedTaskPerformance.query.filter_by(

        employee_id=employee.id

    ).first()



    activity_score=0

    assigned_score=0



    if normal:

        activity_score=normal.performance_percentage



    if assigned:

        assigned_score=(

            assigned.success_percentage

        )



    summary.activity_score=activity_score


    summary.assigned_task_score=assigned_score



    summary.overall_percentage=round(

        (

            activity_score * 0.3

        )

        +

        (

            assigned_score * 0.7

        ),

        2

    )


    summary.grade = summary.performance_grade



    db.session.commit()



    return summary