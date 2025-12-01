//
// Created by bohanleng on 04/11/2025.
//

#ifndef RECONFIGMANUS_MES_SERVER_DEF_H
#define RECONFIGMANUS_MES_SERVER_DEF_H
#include <cstdint>

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

// Used for now
#define MSG_STATION_ACTION_QUERY				0x1046
#define MSG_STATION_ACTION_DONE_QUERY			0x1047

typedef struct
{
	uint32_t        workstation_id;
	uint32_t        tray_id;
} ST_StationActionQuery;

#define MSG_STATION_ACTION_RSP					0x1048

typedef struct
{
	ST_StationActionQuery qry;
	uint32_t    order_id;
	uint32_t    action_type; // 0 for release and read next_station_id, 1 for execute and ignore next_station_id
	uint32_t    next_station_id;
} ST_StationActionRsp;


#endif
