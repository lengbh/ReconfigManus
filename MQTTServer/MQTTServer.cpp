//
// Created by bohanleng on 01/06/2026.
//

#include "MQTTServer.h"
#include "LogMacros.h"
#include <chrono>
#include <mqtt/async_client.h>
#include <thread>
#include <utility>

namespace MQTTConn
{
    namespace
    {
        constexpr int MQTT_QOS = 1;
    }

    class MQTTServerImpl
    {
    public:
        MQTTServerImpl(IMQTTServer & owner, std::string broker_address, std::string client_id)
            : owner_(owner), client_(std::move(broker_address), std::move(client_id)), callback_(owner)
        {
            client_.set_callback(callback_);
        }

        bool Start()
        {
            auto connect_options = mqtt::connect_options_builder::v3()
                .clean_session(true)
                .automatic_reconnect(std::chrono::seconds(1), std::chrono::seconds(30))
                .finalize();

            client_.connect(connect_options)->wait();
            return client_.is_connected();
        }

        void Stop()
        {
            if (!client_.is_connected())
                return;

            try
            {
                client_.disconnect()->wait();
            }
            catch (const mqtt::exception & e)
            {
                ERROR_MSG("[MQTT] Disconnect failed: {}", e.what());
            }
        }

        void Subscribe(const std::string & topic, int qos)
        {
            if (!client_.is_connected())
            {
                ERROR_MSG("[MQTT] Cannot subscribe to {}; broker is not connected.", topic);
                return;
            }
            client_.subscribe(topic, qos)->wait();
        }

        void Publish(const std::string & topic, const std::string & payload, int qos, bool retained)
        {
            if (!client_.is_connected())
            {
                ERROR_MSG("[MQTT] Cannot publish to {}; broker is not connected.", topic);
                return;
            }
            client_.publish(topic, payload.data(), payload.size(), qos, retained);
        }

    private:
        class Callback : public virtual mqtt::callback
        {
        public:
            explicit Callback(IMQTTServer & owner) : owner_(owner) {}

            void connected(const std::string & cause) override
            {
                INFO_MSG("[MQTT] Connected to broker: {}", cause);
            }

            void connection_lost(const std::string & cause) override
            {
                ERROR_MSG("[MQTT] Connection lost: {}", cause);
            }

            void message_arrived(mqtt::const_message_ptr msg) override
            {
                owner_.EnqueueMessage(msg->get_topic(), msg->to_string());
            }

        private:
            IMQTTServer & owner_;
        };

        IMQTTServer & owner_;
        mqtt::async_client client_;
        Callback callback_;
    };

    IMQTTConn::IMQTTConn(std::string topic) : topic_(std::move(topic))
    {
    }

    uint32_t IMQTTConn::GetID() const
    {
        return 0;
    }

    bool IMQTTConn::IsConnected() const
    {
        return true;
    }

    std::string IMQTTConn::GetRemoteEndpoint() const
    {
        return topic_;
    }

    IMQTTServer::IMQTTServer(uint16_t port, std::string broker_host, std::string client_id)
        : port_(port), broker_host_(std::move(broker_host)), client_id_(std::move(client_id))
    {
    }

    IMQTTServer::~IMQTTServer()
    {
        Stop();
    }

    bool IMQTTServer::Start()
    {
        const auto broker_address = "tcp://" + broker_host_ + ":" + std::to_string(port_);
        pimpl_ = std::make_unique<MQTTServerImpl>(*this, broker_address, client_id_);

        try
        {
            running_ = pimpl_->Start();
            if (running_)
                INFO_MSG("[MQTT] Server connected to broker {}", broker_address);
            return running_;
        }
        catch (const mqtt::exception & e)
        {
            running_ = false;
            ERROR_MSG("[MQTT] Failed to connect to broker {}: {}", broker_address, e.what());
            return false;
        }
    }

    void IMQTTServer::Stop()
    {
        running_ = false;
        queue_cv_.notify_all();
        if (pimpl_)
            pimpl_->Stop();
    }

    void IMQTTServer::MessageClient(std::shared_ptr<IMQTTConn> client, const MQTTMsg & msg) const
    {
        if (!client)
        {
            ERROR_MSG("[MQTT] Cannot publish response; MQTT client metadata is empty.");
            return;
        }
        Publish(client->GetRemoteEndpoint(), msg.payload, MQTT_QOS, false);
    }

    void IMQTTServer::MessageAllClients(const MQTTMsg & msg, std::shared_ptr<IMQTTConn> pIgnoreClient) const
    {
        (void)pIgnoreClient;
        Publish(msg.topic, msg.payload, MQTT_QOS, false);
    }

    void IMQTTServer::Update(bool bWait, size_t nMaxMessages)
    {
        size_t message_count = 0;
        while (nMaxMessages == static_cast<size_t>(-1) || message_count < nMaxMessages)
        {
            MQTTMsg msg;
            {
                std::unique_lock lock(queue_mutex_);
                if (bWait)
                {
                    queue_cv_.wait(lock, [this] { return !incoming_messages_.empty() || !running_; });
                    if (!running_ && incoming_messages_.empty())
                        return;
                }
                else if (incoming_messages_.empty())
                {
                    return;
                }

                msg = std::move(incoming_messages_.front());
                incoming_messages_.pop();
            }

            auto client = std::make_shared<IMQTTConn>(msg.topic);
            if (OnClientConnectionRequest(client))
                OnMessage(client, msg);
            ++message_count;
        }
    }

    void IMQTTServer::Run()
    {
        while (running_)
            Update(true);
    }

    void IMQTTServer::Subscribe(const std::string & topic, int qos) const
    {
        if (pimpl_)
            pimpl_->Subscribe(topic, qos);
    }

    void IMQTTServer::Publish(const std::string & topic, const std::string & payload, int qos, bool retained) const
    {
        if (pimpl_)
            pimpl_->Publish(topic, payload, qos, retained);
    }

    void IMQTTServer::EnqueueMessage(const std::string & topic, const std::string & payload)
    {
        {
            std::lock_guard lock(queue_mutex_);
            incoming_messages_.push(MQTTMsg{topic, payload});
        }
        queue_cv_.notify_one();
    }
}
