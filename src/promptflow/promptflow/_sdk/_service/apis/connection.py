# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import inspect

from flask import jsonify, request

from promptflow._sdk._errors import ConnectionNotFoundError
from promptflow._sdk._service import Namespace, Resource, fields
from promptflow._sdk._service.utils.utils import local_user_only
from promptflow._sdk.entities._connection import _Connection
from promptflow._sdk.operations._connection_operations import ConnectionOperations
import promptflow._sdk.schemas._connection as connection


api = Namespace("Connections", description="Connections Management")

# Response model of list connections
list_connection_field = api.model(
    "Connection",
    {
        "name": fields.String,
        "type": fields.String,
        "module": fields.String,
        "expiry_time": fields.DateTime(),
        "created_date": fields.DateTime(),
        "last_modified_date": fields.DateTime(),
    },
)
# Response model of connection operation
dict_field = api.schema_model("ConnectionDict", {"additionalProperties": True, "type": "object"})
# Response model of connection spec
connection_config_spec_model = api.model(
    "ConnectionConfigSpec",
    {
        "name": fields.String,
        "optional": fields.Boolean,
        "default": fields.String,
    },
)
connection_spec_model = api.model(
    "ConnectionSpec",
    {
        "connection_type": fields.String,
        "config_spec": fields.List(fields.Nested(connection_config_spec_model)),
    },
)


@api.errorhandler(ConnectionNotFoundError)
def handle_connection_not_found_exception(error):
    api.logger.warning(f"Raise ConnectionNotFoundError, {error.message}")
    return {"error_message": error.message}, 404


@api.route("/")
class ConnectionList(Resource):
    @api.doc(description="List all connection")
    @api.marshal_with(list_connection_field, skip_none=True, as_list=True)
    @local_user_only
    def get(self):
        connection_op = ConnectionOperations()
        # parse query parameters
        max_results = request.args.get("max_results", default=50, type=int)
        all_results = request.args.get("all_results", default=False, type=bool)

        connections = connection_op.list(max_results=max_results, all_results=all_results)
        connections_dict = [connection._to_dict() for connection in connections]
        return connections_dict


@api.route("/<string:name>")
@api.param("name", "The connection name.")
class Connection(Resource):
    @api.doc(description="Get connection")
    @api.response(code=200, description="Connection details", model=dict_field)
    @local_user_only
    def get(self, name: str):
        connection_op = ConnectionOperations()
        connection = connection_op.get(name=name, raise_error=True)
        connection_dict = connection._to_dict()
        return jsonify(connection_dict)

    @api.doc(body=dict_field, description="Create connection")
    @api.response(code=200, description="Connection details", model=dict_field)
    @local_user_only
    def post(self, name: str):
        connection_op = ConnectionOperations()
        connection_data = request.get_json(force=True)
        connection_data["name"] = name
        connection = _Connection._load(data=connection_data)
        connection = connection_op.create_or_update(connection)
        return jsonify(connection._to_dict())

    @api.doc(body=dict_field, description="Update connection")
    @api.response(code=200, description="Connection details", model=dict_field)
    @local_user_only
    def put(self, name: str):
        connection_op = ConnectionOperations()
        connection_dict = request.get_json(force=True)
        params_override = [{k: v} for k, v in connection_dict.items()]
        existing_connection = connection_op.get(name)
        connection = _Connection._load(data=existing_connection._to_dict(), params_override=params_override)
        connection._secrets = existing_connection._secrets
        connection = connection_op.create_or_update(connection)
        return jsonify(connection._to_dict())

    @api.doc(description="Delete connection")
    @local_user_only
    def delete(self, name: str):
        connection_op = ConnectionOperations()
        connection_op.delete(name=name)


@api.route("/<string:name>/listsecrets")
class ConnectionWithSecret(Resource):
    @api.doc(description="Get connection with secret")
    @api.response(code=200, description="Connection details with secret", model=dict_field)
    @local_user_only
    def get(self, name: str):
        connection_op = ConnectionOperations()
        connection = connection_op.get(name=name, with_secrets=True, raise_error=True)
        connection_dict = connection._to_dict()
        return jsonify(connection_dict)


@api.route("/specs")
class ConnectionSpecs(Resource):
    @api.doc(description="List connection spec")
    @api.response(code=200, description="List connection spec", skip_none=True, model=connection_spec_model)
    def get(self):
        hide_connection_fields = ["module"]
        connection_specs = []
        for name, obj in inspect.getmembers(connection):
            if (
                inspect.isclass(obj)
                and issubclass(obj, connection.ConnectionSchema)
                and not isinstance(obj, connection.ConnectionSchema)
            ):
                config_specs = []
                for field_name, field in obj._declared_fields.items():
                    if not field.dump_only and field_name not in hide_connection_fields:
                        configs = {"name": field_name, "optional": field.allow_none}
                        if field.default:
                            configs["default"] = field.default
                        if field_name == "type":
                            configs["default"] = field.allowed_values[0]
                        config_specs.append(configs)
                connection_spec = {
                    "connection_type": name.replace("Schema", ""),
                    "config_specs": config_specs,
                }
                connection_specs.append(connection_spec)
        return jsonify(connection_specs)
