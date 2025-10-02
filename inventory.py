# inventory.py
import sqlite3
from datetime import datetime

from db import connect as _connect


def get_all_items():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
          SELECT
      i.item_id, i.name, i.description,
      i.unit_cost, i.unit_price,
      IFNULL(SUM(sm.change_qty),0) AS on_hand,
      i.reorder_threshold
        FROM items i
        LEFT JOIN stock_movements sm ON i.item_id=sm.item_id
        GROUP BY i.item_id
    """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def items_below_reorder():
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
        SELECT
      i.item_id, i.name, i.description,
      i.unit_cost, i.unit_price,
      IFNULL(SUM(sm.change_qty),0) AS on_hand,
      i.reorder_threshold
        FROM items i
        LEFT JOIN stock_movements sm ON i.item_id=sm.item_id
        GROUP BY i.item_id
        HAVING on_hand <= i.reorder_threshold
    """
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def create_item(name, description, cost, price, threshold):
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
      INSERT INTO items
        (name,description,unit_cost,unit_price,reorder_threshold)
      VALUES (?,?,?,?,?)
    """,
        (name, description, cost, price, threshold),
    )
    conn.commit()
    conn.close()


def update_item(item_id, **fields):
    cols, vals = zip(*fields.items())
    set_clause = ", ".join(f"{col}=?" for col in cols)
    conn = _connect()
    cur = conn.cursor()
    cur.execute(f"UPDATE items SET {set_clause} WHERE item_id=?", (*vals, item_id))
    conn.commit()
    conn.close()


def delete_item(item_id):
    conn = _connect()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE item_id=?", (item_id,))
    conn.commit()
    conn.close()


def adjust_stock(item_id, change_qty, reason=None):
    ts = datetime.now().isoformat(" ", "seconds")
    conn = _connect()
    cur = conn.cursor()
    cur.execute(
        """
      INSERT INTO stock_movements
        (item_id,change_qty,reason,timestamp)
      VALUES (?,?,?,?)
    """,
        (item_id, change_qty, reason, ts),
    )
    conn.commit()
    conn.close()
