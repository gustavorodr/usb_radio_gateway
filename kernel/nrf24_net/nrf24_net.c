// SPDX-License-Identifier: GPL-2.0
// Minimal skeleton of a kernel net_device driver for nRF24L01 over SPI
// This module creates a netdev (nrf0) and stubs SPI TX/RX paths.
// NOTE: Hardware SPI glue is TODO. This is a starting point to move data
// in-kernel, avoiding userspace overhead for lowest possible latency.

#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/netdevice.h>
#include <linux/etherdevice.h>
#include <linux/skbuff.h>
#include <linux/spi/spi.h>
#include <linux/kthread.h>
#include <linux/delay.h>
#include <linux/mutex.h>
#include <linux/if_ether.h>

#define DRV_NAME "nrf24_net"
#define NRF_PAYLOAD 32
#define HDR_SIZE 4
#define FRAG_SIZE (NRF_PAYLOAD - HDR_SIZE)

struct nrf24_priv {
	struct net_device *ndev;
	struct spi_device *spi;
	struct task_struct *rx_thread;
	struct mutex tx_lock;
	u16 msg_id;
	bool running;
};

static int nrf24_hw_init(struct nrf24_priv *priv)
{
	// TODO: configure radio via SPI (addresses, channel, data rate, auto-ack)
	return 0;
}

static int nrf24_hw_send_frame(struct nrf24_priv *priv, const u8 *buf)
{
	// TODO: spi_sync to TX a 32-byte frame
	udelay(200); // simulate air/tx time; remove when real SPI in place
	return 0; // 0 = success
}

static int nrf24_hw_recv_frame(struct nrf24_priv *priv, u8 *buf)
{
	// TODO: Read RX FIFO if available, 32-byte frame
	// Return 1 if a frame was read, 0 if none, <0 on error
	return 0;
}

static netdev_tx_t nrf24_start_xmit(struct sk_buff *skb, struct net_device *ndev)
{
	struct nrf24_priv *priv = netdev_priv(ndev);
	int len = skb->len;
	const u8 *data = skb->data;
	u16 msg_id;
	int offset = 0;
	int frags, i;
	u8 frame[NRF_PAYLOAD];
	int ret;

	if (!netif_carrier_ok(ndev)) {
		ndev->stats.tx_dropped++;
		dev_kfree_skb(skb);
		return NETDEV_TX_OK;
	}

	mutex_lock(&priv->tx_lock);
	msg_id = ++priv->msg_id;
	frags = DIV_ROUND_UP(len, FRAG_SIZE);
	for (i = 0; i < frags; i++) {
		int chunk = min(FRAG_SIZE, len - offset);
		// Header: msg_id (2B), frag_idx (1B), frag_count (1B)
		frame[0] = (msg_id >> 8) & 0xFF;
		frame[1] = msg_id & 0xFF;
		frame[2] = i & 0xFF;
		frame[3] = frags & 0xFF;
		memset(frame + HDR_SIZE, 0, FRAG_SIZE);
		memcpy(frame + HDR_SIZE, data + offset, chunk);
		ret = nrf24_hw_send_frame(priv, frame);
		if (ret) {
			ndev->stats.tx_errors++;
			break;
		}
		offset += chunk;
		ndev->stats.tx_packets++;
		ndev->stats.tx_bytes += chunk;
	}
	mutex_unlock(&priv->tx_lock);

	dev_kfree_skb(skb);
	return NETDEV_TX_OK;
}

static int nrf24_open(struct net_device *ndev)
{
	struct nrf24_priv *priv = netdev_priv(ndev);
	int ret;

	ret = nrf24_hw_init(priv);
	if (ret)
		return ret;
	priv->running = true;
	netif_start_queue(ndev);
	netif_carrier_on(ndev);
	return 0;
}

static int nrf24_stop(struct net_device *ndev)
{
	struct nrf24_priv *priv = netdev_priv(ndev);
	priv->running = false;
	netif_stop_queue(ndev);
	netif_carrier_off(ndev);
	return 0;
}

static const struct net_device_ops nrf24_netdev_ops = {
	.ndo_open = nrf24_open,
	.ndo_stop = nrf24_stop,
	.ndo_start_xmit = nrf24_start_xmit,
};

static int nrf24_rx_thread_fn(void *data)
{
	struct nrf24_priv *priv = data;
	u8 frame[NRF_PAYLOAD];

	while (!kthread_should_stop()) {
		int got = nrf24_hw_recv_frame(priv, frame);
		if (got > 0) {
			// TODO: Reassembly buffer and emit skb when complete
			// For now, drop (skeleton)
			continue;
		}
		// Sleep briefly to avoid busy loop; reduce for lower latency once HW ready
		usleep_range(500, 1000);
	}
	return 0;
}

static void nrf24_setup(struct net_device *ndev)
{
	ether_setup(ndev);
	ndev->netdev_ops = &nrf24_netdev_ops;
	ndev->mtu = 1500;
	// Generate a locally administered MAC
	eth_hw_addr_random(ndev);
}

static int nrf24_probe(struct spi_device *spi)
{
	struct net_device *ndev;
	struct nrf24_priv *priv;
	int ret;

	ndev = alloc_netdev(sizeof(*priv), "nrf%d", NET_NAME_ENUM, nrf24_setup);
	if (!ndev)
		return -ENOMEM;
	priv = netdev_priv(ndev);
	priv->ndev = ndev;
	priv->spi = spi;
	mutex_init(&priv->tx_lock);

	ret = register_netdev(ndev);
	if (ret) {
		free_netdev(ndev);
		return ret;
	}

	spi_set_drvdata(spi, ndev);
	priv->rx_thread = kthread_run(nrf24_rx_thread_fn, priv, DRV_NAME "_rx");
	if (IS_ERR(priv->rx_thread)) {
		unregister_netdev(ndev);
		free_netdev(ndev);
		return PTR_ERR(priv->rx_thread);
	}

	dev_info(&spi->dev, "nrf24_net device registered as %s\n", ndev->name);
	return 0;
}

static int nrf24_remove(struct spi_device *spi)
{
	struct net_device *ndev = spi_get_drvdata(spi);
	struct nrf24_priv *priv = netdev_priv(ndev);

	if (priv->rx_thread)
		kthread_stop(priv->rx_thread);
	unregister_netdev(ndev);
	free_netdev(ndev);
	return 0;
}

static const struct of_device_id nrf24_of_match[] = {
	{ .compatible = "nordic,nrf24l01" },
	{ /* sentinel */ }
};
MODULE_DEVICE_TABLE(of, nrf24_of_match);

static struct spi_driver nrf24_driver = {
	.driver = {
		.name = DRV_NAME,
		.of_match_table = nrf24_of_match,
	},
	.probe = nrf24_probe,
	.remove = nrf24_remove,
};

module_spi_driver(nrf24_driver);

MODULE_AUTHOR("usb_radio_gateway");
MODULE_DESCRIPTION("nRF24L01 net_device skeleton for low-latency in-kernel TUN");
MODULE_LICENSE("GPL");
