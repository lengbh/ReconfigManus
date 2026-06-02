//
// Created by bohanleng on 04/11/2025.
//

#ifndef RECONFIGMANUS_MES_SERVER_DEF_H
#define RECONFIGMANUS_MES_SERVER_DEF_H
#include "MQTTServer.h"
#include <cstdint>
#include <nlohmann/json.hpp>
#include <string>

// order run status
enum ORDER_RUN_STATUS
{
	ORDER_WAIT,
	ORDER_EXECUTING,
	ORDER_FINISHED,
	ORDER_ERROR,
	ORDER_DELETE
};

typedef struct
{
	uint32_t	tray_id;
	bool		executing_order;
	uint32_t	current_order_id;
} ST_TrayInfo;

// TODO simplest number to represent process for now
typedef uint8_t ST_ProcessInfo;

#define MSG_STATION_ACTION_QUERY                0x1046
#define MSG_STATION_ACTION_DONE_QUERY           0x1047

typedef struct
{
	uint32_t        workstation_id;
	uint32_t        tray_id;
} ST_StationActionQuery;

#define MSG_STATION_ACTION_RSP                  0x1048

typedef struct
{
	ST_StationActionQuery qry;
	uint32_t    order_id;
	uint32_t    action_type; // 0 for release and read next_station_id, 1 for execute and ignore next_station_id
	uint32_t    next_station_id;
} ST_StationActionRsp;

typedef struct
{
	std::string request_id;
	std::string reply_to;
	ST_StationActionQuery qry;
} ST_StationActionQueryFrame;

typedef struct
{
	std::string request_id;
	std::string reply_to;
	ST_StationActionQuery qry;
} ST_StationActionDoneQueryFrame;

typedef struct
{
	std::string request_id;
	std::string reply_to;
	ST_StationActionRsp rsp;
} ST_StationActionRspFrame;

inline void DecodeStationActionRequestPayload(const std::string & payload,
                                              std::string & request_id,
                                              std::string & reply_to,
                                              ST_StationActionQuery & qry)
{
	const auto request = nlohmann::json::parse(payload);
	qry.workstation_id = request.at("workstation_id").get<uint32_t>();
	qry.tray_id = request.at("tray_id").get<uint32_t>();
	request_id = request.at("request_id").get<std::string>();
	reply_to = request.at("reply_to").get<std::string>();
}

inline MQTTConn::MQTTMsg & operator >> (MQTTConn::MQTTMsg & msg, ST_StationActionQueryFrame & frame)
{
	DecodeStationActionRequestPayload(msg.payload, frame.request_id, frame.reply_to, frame.qry);
	return msg;
}

inline MQTTConn::MQTTMsg & operator >> (MQTTConn::MQTTMsg & msg, ST_StationActionDoneQueryFrame & frame)
{
	DecodeStationActionRequestPayload(msg.payload, frame.request_id, frame.reply_to, frame.qry);
	return msg;
}

inline MQTTConn::MQTTMsg & operator << (MQTTConn::MQTTMsg & msg, const ST_StationActionRspFrame & frame)
{
	msg.topic = frame.reply_to;
	nlohmann::json response = {
		{"schema_version", 1},
		{"request_id", frame.request_id},
		{"workstation_id", frame.rsp.qry.workstation_id},
		{"tray_id", frame.rsp.qry.tray_id},
		{"order_id", frame.rsp.order_id},
		{"action_type", frame.rsp.action_type},
		{"next_station_id", frame.rsp.next_station_id}
	};
	msg.payload = response.dump();
	return msg;
}

#endif
