import React from 'react';
import { View, Text, StyleSheet } from 'react-native';

export function Card({ children, style }: any) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function CardHeader({ children, style }: any) {
  return <View style={[styles.header, style]}>{children}</View>;
}

export function CardTitle({ children, style }: any) {
  return <Text style={[styles.title, style]}>{children}</Text>;
}

export function CardDescription({ children, style }: any) {
  return <Text style={[styles.description, style]}>{children}</Text>;
}

export function CardContent({ children, style }: any) {
  return <View style={[styles.content, style]}>{children}</View>;
}

const styles = StyleSheet.create({
  card: { backgroundColor: 'rgba(16, 9, 28, 0.88)', borderRadius: 8, padding: 16, marginVertical: 8 },
  header: { marginBottom: 12 },
  title: { color: '#fff', fontSize: 18, fontWeight: 'bold' },
  description: { color: '#68779b', fontSize: 14, marginTop: 4 },
  content: { paddingTop: 8 },
});
