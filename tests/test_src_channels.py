import logging

import channels
import pytest

class TestCommChannel(channels.CommChannel):

    started = False

    def start(self) -> None:
        self.started = True

    def stop(self) -> None:
        raise NotImplementedError()

    def receive(self) -> str:
        raise NotImplementedError()

    def send(self, message: str) -> None:
        raise NotImplementedError()


def test_commchannel_config():
    channel = TestCommChannel()
    channels.registerCommChannel("Test", channel)
    channels.commChannelStart("Test")
    assert channel.started


def test_commchannel_send_logs_success_without_message_content(caplog):
    caplog.set_level(logging.INFO)

    class SuccessfulChannel(TestCommChannel):
        def send(self, message: str) -> None:
            self.message = message

    channel = SuccessfulChannel()
    channels.registerCommChannel("Successful", channel)
    channels.commChannelStart("Successful")

    channels.commChannelSend("private message")

    assert channel.message == "private message"
    assert "[CHANNEL_SEND] dispatch_succeeded=true chars=15" in caplog.text
    assert "private message" not in caplog.text


def test_commchannel_send_logs_and_preserves_failure(caplog):
    class FailingChannel(TestCommChannel):
        def send(self, message: str) -> None:
            raise RuntimeError("delivery failed")

    channels.registerCommChannel("Failing", FailingChannel())
    channels.commChannelStart("Failing")

    with pytest.raises(RuntimeError, match="delivery failed"):
        channels.commChannelSend("message")

    assert "[CHANNEL_SEND] dispatch_succeeded=false chars=7" in caplog.text
