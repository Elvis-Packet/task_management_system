from flask import jsonify


def ok(data=None, message="", status=200):
    return jsonify({"success": True, "message": message, "data": data}), status


def err(message, status=400, errors=None):
    return jsonify({"success": False, "message": message, "errors": errors}), status
