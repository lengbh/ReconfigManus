//
// Created by bohanleng on 01/06/2026.
//

#ifndef RECONFIGMANUS_MQTT_SERVER_H
#define RECONFIGMANUS_MQTT_SERVER_H

#include <condition_variable>
#include <cstdint>
#include <memory>
#include <mutex>
#include <queue>
#include <string>

namespace MQTTConn
{
    struct MQTTMsg
    {
        std::string topic;
        std::string payload;
    };

    class IMQTTConn
    {
    public:
        explicit IMQTTConn(std::string topic);

        [[nodiscard]] uint32_t GetID() const;
        [[nodiscard]] bool IsConnected() const;
        [[nodiscard]] std::string GetRemoteEndpoint() const;

    private:
        std::string topic_;
    };

    class IMQTTServer
    {
        friend class MQTTServerImpl;

    public:
        explicit IMQTTServer(uint16_t port, std::string broker_host = "localhost", std::string client_id = "mqtt-server");
        virtual ~IMQTTServer();

        bool Start();
        void Stop();

        void MessageClient(std::shared_ptr<IMQTTConn> client, const MQTTMsg & msg) const;
        void MessageAllClients(const MQTTMsg & msg, std::shared_ptr<IMQTTConn> pIgnoreClient = nullptr) const;

        void Update(bool bWait, size_t nMaxMessages = -1);
        void Run();

        void Subscribe(const std::string & topic, int qos = 1) const;
        void Publish(const std::string & topic, const std::string & payload, int qos = 1, bool retained = false) const;

        virtual bool OnClientConnectionRequest(std::shared_ptr<IMQTTConn> client) { return true; }
        virtual void OnClientConnected(std::shared_ptr<IMQTTConn> client) {}
        virtual void OnClientDisconnected(std::shared_ptr<IMQTTConn> client) {}
        virtual void OnMessage(std::shared_ptr<IMQTTConn> client, MQTTMsg & msg) = 0;

    private:
        void EnqueueMessage(const std::string & topic, const std::string & payload);

        uint16_t port_;
        std::string broker_host_;
        std::string client_id_;

        bool running_{false};
        std::unique_ptr<class MQTTServerImpl> pimpl_;

        mutable std::mutex queue_mutex_;
        std::condition_variable queue_cv_;
        std::queue<MQTTMsg> incoming_messages_;
    };
}

#endif //RECONFIGMANUS_MQTT_SERVER_H
