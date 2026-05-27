# ruff: noqa
"""gRPC bindings for survey/v1/survey.proto."""

from app.grpc.gen import survey_pb2 as survey__pb2


class SurveyServiceStub:
    def __init__(self, channel):
        self.GetSurveyResult = channel.unary_unary(
            "/ontheblock.survey.v1.SurveyService/GetSurveyResult",
            request_serializer=survey__pb2.GetSurveyResultRequest.SerializeToString,
            response_deserializer=survey__pb2.GetSurveyResultResponse.FromString,
        )
        self.GetSurveyResultByUser = channel.unary_unary(
            "/ontheblock.survey.v1.SurveyService/GetSurveyResultByUser",
            request_serializer=(
                survey__pb2.GetSurveyResultByUserRequest.SerializeToString
            ),
            response_deserializer=survey__pb2.GetSurveyResultResponse.FromString,
        )
