import json

from flask_restful import Resource, marshal_with, reqparse
from flask_restful.inputs import int_range
from sqlalchemy.orm import Session
from werkzeug.exceptions import BadRequest, NotFound

import services
from controllers.service_api import api
from controllers.service_api.app.error import NotChatAppError
from controllers.service_api.wraps import FetchUserArg, WhereisUserArg, validate_app_token
from core.app.entities.app_invoke_entities import InvokeFrom
from extensions.ext_database import db
from fields.conversation_fields import (
    conversation_delete_fields,
    conversation_infinite_scroll_pagination_fields,
    simple_conversation_fields,
)
from fields.conversation_variable_fields import (
    conversation_variable_fields,
    conversation_variable_infinite_scroll_pagination_fields,
)
from libs.helper import uuid_value
from models.model import App, AppMode, EndUser
from services.conversation_service import ConversationService


class ConversationApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.QUERY))
    @marshal_with(conversation_infinite_scroll_pagination_fields)
    def get(self, app_model: App, end_user: EndUser):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        parser = reqparse.RequestParser()
        parser.add_argument("last_id", type=uuid_value, location="args")
        parser.add_argument("limit", type=int_range(1, 100), required=False, default=20, location="args")
        parser.add_argument(
            "sort_by",
            type=str,
            choices=["created_at", "-created_at", "updated_at", "-updated_at"],
            required=False,
            default="-updated_at",
            location="args",
        )
        args = parser.parse_args()

        try:
            with Session(db.engine) as session:
                return ConversationService.pagination_by_last_id(
                    session=session,
                    app_model=app_model,
                    user=end_user,
                    last_id=args["last_id"],
                    limit=args["limit"],
                    invoke_from=InvokeFrom.SERVICE_API,
                    sort_by=args["sort_by"],
                )
        except services.errors.conversation.LastConversationNotExistsError:
            raise NotFound("Last Conversation Not Exists.")


class ConversationDetailApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON))
    @marshal_with(conversation_delete_fields)
    def delete(self, app_model: App, end_user: EndUser, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)

        try:
            ConversationService.delete(app_model, conversation_id, end_user)
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        return {"result": "success"}, 204


class ConversationRenameApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON))
    @marshal_with(simple_conversation_fields)
    def post(self, app_model: App, end_user: EndUser, c_id):
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)

        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=False, location="json")
        parser.add_argument("auto_generate", type=bool, required=False, default=False, location="json")
        args = parser.parse_args()

        try:
            return ConversationService.rename(app_model, conversation_id, end_user, args["name"], args["auto_generate"])
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")


class ConversationVariablesApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.QUERY))
    @marshal_with(conversation_variable_infinite_scroll_pagination_fields)
    def get(self, app_model: App, end_user: EndUser, c_id):
        # conversational variable only for chat app
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)

        parser = reqparse.RequestParser()
        parser.add_argument("last_id", type=uuid_value, location="args")
        parser.add_argument("limit", type=int_range(1, 100), required=False, default=20, location="args")
        args = parser.parse_args()

        try:
            return ConversationService.get_conversational_variable(
                app_model, conversation_id, end_user, args["limit"], args["last_id"]
            )
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")


class ConversationVariableDetailApi(Resource):
    @validate_app_token(fetch_user_arg=FetchUserArg(fetch_from=WhereisUserArg.JSON))
    @marshal_with(conversation_variable_fields)
    def put(self, app_model: App, end_user: EndUser, c_id, variable_id):
        """Update a conversation variable's value"""
        app_mode = AppMode.value_of(app_model.mode)
        if app_mode not in {AppMode.CHAT, AppMode.AGENT_CHAT, AppMode.ADVANCED_CHAT}:
            raise NotChatAppError()

        conversation_id = str(c_id)
        variable_id = str(variable_id)

        parser = reqparse.RequestParser()
        parser.add_argument("value", required=True, location="json")
        args = parser.parse_args()

        try:
            return ConversationService.update_conversation_variable(
                app_model, conversation_id, variable_id, end_user, json.loads(args["value"])
            )
        except services.errors.conversation.ConversationNotExistsError:
            raise NotFound("Conversation Not Exists.")
        except services.errors.conversation.ConversationVariableNotExistsError:
            raise NotFound("Conversation Variable Not Exists.")
        except services.errors.conversation.ConversationVariableTypeMismatchError as e:
            raise BadRequest(str(e))


api.add_resource(ConversationRenameApi, "/conversations/<uuid:c_id>/name", endpoint="conversation_name")
api.add_resource(ConversationApi, "/conversations")
api.add_resource(ConversationDetailApi, "/conversations/<uuid:c_id>", endpoint="conversation_detail")
api.add_resource(ConversationVariablesApi, "/conversations/<uuid:c_id>/variables", endpoint="conversation_variables")
api.add_resource(
    ConversationVariableDetailApi,
    "/conversations/<uuid:c_id>/variables/<uuid:variable_id>",
    endpoint="conversation_variable_detail",
    methods=["PUT"],
)
