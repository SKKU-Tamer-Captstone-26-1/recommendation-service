# ruff: noqa
"""gRPC bindings for recommendation/v1/recommendation.proto."""

import grpc

from app.grpc.gen import recommendation_pb2 as recommendation__pb2


class RecommendationServiceStub:
    def __init__(self, channel):
        self.GetProfileStatus = channel.unary_unary(
            "/ontheblock.recommendation.v1.RecommendationService/GetProfileStatus",
            request_serializer=recommendation__pb2.GetProfileStatusRequest.SerializeToString,
            response_deserializer=recommendation__pb2.GetProfileStatusResponse.FromString,
        )
        self.GetBeverageRecommendations = channel.unary_unary(
            "/ontheblock.recommendation.v1.RecommendationService/GetBeverageRecommendations",
            request_serializer=(
                recommendation__pb2.GetBeverageRecommendationsRequest.SerializeToString
            ),
            response_deserializer=(
                recommendation__pb2.GetBeverageRecommendationsResponse.FromString
            ),
        )
        self.GetVenueRecommendations = channel.unary_unary(
            "/ontheblock.recommendation.v1.RecommendationService/GetVenueRecommendations",
            request_serializer=(
                recommendation__pb2.GetVenueRecommendationsRequest.SerializeToString
            ),
            response_deserializer=(
                recommendation__pb2.GetVenueRecommendationsResponse.FromString
            ),
        )
        self.RecordRecommendationEvent = channel.unary_unary(
            "/ontheblock.recommendation.v1.RecommendationService/RecordRecommendationEvent",
            request_serializer=recommendation__pb2.RecordRecommendationEventRequest.SerializeToString,
            response_deserializer=recommendation__pb2.RecordRecommendationEventResponse.FromString,
        )


class RecommendationServiceServicer:
    def GetProfileStatus(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "method not implemented")

    def GetBeverageRecommendations(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "method not implemented")

    def GetVenueRecommendations(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "method not implemented")

    def RecordRecommendationEvent(self, request, context):
        context.abort(grpc.StatusCode.UNIMPLEMENTED, "method not implemented")


def add_RecommendationServiceServicer_to_server(servicer, server):
    rpc_method_handlers = {
        "GetProfileStatus": grpc.unary_unary_rpc_method_handler(
            servicer.GetProfileStatus,
            request_deserializer=recommendation__pb2.GetProfileStatusRequest.FromString,
            response_serializer=recommendation__pb2.GetProfileStatusResponse.SerializeToString,
        ),
        "GetBeverageRecommendations": grpc.unary_unary_rpc_method_handler(
            servicer.GetBeverageRecommendations,
            request_deserializer=(
                recommendation__pb2.GetBeverageRecommendationsRequest.FromString
            ),
            response_serializer=(
                recommendation__pb2.GetBeverageRecommendationsResponse.SerializeToString
            ),
        ),
        "GetVenueRecommendations": grpc.unary_unary_rpc_method_handler(
            servicer.GetVenueRecommendations,
            request_deserializer=(
                recommendation__pb2.GetVenueRecommendationsRequest.FromString
            ),
            response_serializer=(
                recommendation__pb2.GetVenueRecommendationsResponse.SerializeToString
            ),
        ),
        "RecordRecommendationEvent": grpc.unary_unary_rpc_method_handler(
            servicer.RecordRecommendationEvent,
            request_deserializer=(
                recommendation__pb2.RecordRecommendationEventRequest.FromString
            ),
            response_serializer=(
                recommendation__pb2.RecordRecommendationEventResponse.SerializeToString
            ),
        ),
    }
    generic_handler = grpc.method_handlers_generic_handler(
        "ontheblock.recommendation.v1.RecommendationService",
        rpc_method_handlers,
    )
    server.add_generic_rpc_handlers((generic_handler,))
