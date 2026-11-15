import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

// Android emulator: 10.0.2.2. iOS simulator: 127.0.0.1.
// For a physical phone, replace with your development computer's LAN IP.
const apiBaseUrl = 'http://10.0.2.2:8000';

void main() => runApp(const SocietyRegistryApp());

class SocietyRegistryApp extends StatelessWidget {
  const SocietyRegistryApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Society Guest Registry',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(colorSchemeSeed: const Color(0xFF175C4A),
        useMaterial3: true),
      home: const DashboardPage(),
    );
  }
}

class DashboardPage extends StatefulWidget {
  const DashboardPage({super.key});
  @override
  State<DashboardPage> createState() => _DashboardPageState();
}

class _DashboardPageState extends State<DashboardPage> {
  String apiStatus = 'Checking backend...';

  @override
  void initState() {
    super.initState();
    checkBackend();
  }

  Future<void> checkBackend() async {
    try {
      final response = await http.get(Uri.parse('$apiBaseUrl/health'))
          .timeout(const Duration(seconds: 5));
      final data = jsonDecode(response.body);
      if (mounted) setState(() => apiStatus =
          response.statusCode == 200 ? 'Connected: ${data['status']}' : 'API error');
    } catch (_) {
      if (mounted) setState(() => apiStatus =
          'Not connected. Check API URL and network.');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Society Guest Registry')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Card(
            color: Theme.of(context).colorScheme.primaryContainer,
            child: const Padding(
              padding: EdgeInsets.all(18),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Welcome to your society gate',
                    style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold)),
                  SizedBox(height: 6),
                  Text('Manage guest arrivals, approvals and departures.'),
                ]),
            ),
          ),
          const SizedBox(height: 12),
          Card(child: ListTile(
            leading: const Icon(Icons.cloud_outlined),
            title: const Text('Backend connection'),
            subtitle: Text(apiStatus),
            trailing: IconButton(icon: const Icon(Icons.refresh),
              onPressed: checkBackend),
          )),
          const SizedBox(height: 12),
          const Text('Quick actions',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
          const SizedBox(height: 8),
          _ActionTile(icon: Icons.person_add_alt_1,
            title: 'Register visitor',
            subtitle: 'Record a guest at the society gate',
            onTap: () => _showComingSoon(context)),
          _ActionTile(icon: Icons.fact_check_outlined,
            title: 'Pending approvals',
            subtitle: 'Review visitors awaiting resident approval',
            onTap: () => _showComingSoon(context)),
          _ActionTile(icon: Icons.qr_code_scanner,
            title: 'Scan visitor pass',
            subtitle: 'Verify a visitor QR pass',
            onTap: () => _showComingSoon(context)),
          _ActionTile(icon: Icons.logout,
            title: 'Visitor check-out',
            subtitle: 'Record a guest departure',
            onTap: () => _showComingSoon(context)),
        ],
      ),
    );
  }

  void _showComingSoon(BuildContext context) {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('This module is in the next implementation stage.')),
    );
  }
}

class _ActionTile extends StatelessWidget {
  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;
  const _ActionTile({required this.icon, required this.title,
    required this.subtitle, required this.onTap});

  @override
  Widget build(BuildContext context) => Card(
    child: ListTile(
      leading: CircleAvatar(child: Icon(icon)),
      title: Text(title),
      subtitle: Text(subtitle),
      trailing: const Icon(Icons.chevron_right),
      onTap: onTap,
    ),
  );
}
