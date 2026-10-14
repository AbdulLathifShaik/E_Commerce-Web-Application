CREATE TABLE IF NOT EXISTS usercreate (
  username VARCHAR(50) NOT NULL,
  user_email VARCHAR(100) NOT NULL,
  address TEXT NOT NULL,
  password VARCHAR(255) NOT NULL,
  gender ENUM('Male','Female') DEFAULT NULL,
  PRIMARY KEY (user_email),
  UNIQUE KEY username (username)
);
CREATE TABLE IF NOT EXISTS admincreate (
  email VARCHAR(100) NOT NULL,
  username VARCHAR(100) NOT NULL,
  password VARCHAR(255) NOT NULL,
  address TEXT NOT NULL,
  accept ENUM('on','off') DEFAULT NULL,
  dp_image VARCHAR(100) DEFAULT NULL,
  ph_no BIGINT DEFAULT NULL,
  PRIMARY KEY (email),
  UNIQUE KEY ph_no (ph_no)
);
CREATE TABLE IF NOT EXISTS contactus (
  name VARCHAR(100) DEFAULT NULL,
  email VARCHAR(100) DEFAULT NULL,
  message TEXT
);
CREATE TABLE IF NOT EXISTS items (
  item_id BINARY(16) NOT NULL,
  item_name VARCHAR(255) NOT NULL,
  quantity INT UNSIGNED DEFAULT NULL,
  price DECIMAL(14,2) NOT NULL,
  category ENUM('Home_appliances','Electronics','Fashion','Grocery') DEFAULT NULL,
  image_name VARCHAR(255) NOT NULL,
  added_by VARCHAR(100) DEFAULT NULL,
  description LONGTEXT,
  PRIMARY KEY (item_id),
  KEY added_by (added_by),
  CONSTRAINT items_ibfk_1 FOREIGN KEY (added_by) REFERENCES admincreate (email) ON DELETE CASCADE ON UPDATE CASCADE
);
CREATE TABLE IF NOT EXISTS orders (
  orderid BIGINT NOT NULL AUTO_INCREMENT,
  itemid BINARY(16) DEFAULT NULL,
  item_name VARCHAR(255) DEFAULT NULL,
  qty INT DEFAULT NULL,
  total_price DECIMAL(14,2) DEFAULT NULL,
  user VARCHAR(100) DEFAULT NULL,
  ordered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (orderid),
  KEY user (user),
  KEY itemid (itemid),
  CONSTRAINT orders_ibfk_1 FOREIGN KEY (user) REFERENCES usercreate (user_email) ON DELETE CASCADE,
  CONSTRAINT orders_ibfk_2 FOREIGN KEY (itemid) REFERENCES items (item_id) ON DELETE SET NULL
);
CREATE TABLE IF NOT EXISTS reviews (
  username VARCHAR(100) NOT NULL,
  itemid BINARY(16) NOT NULL,
  title TINYTEXT,
  review TEXT,
  rating INT DEFAULT NULL,
  date DATETIME DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (itemid, username),
  KEY username (username),
  CONSTRAINT reviews_ibfk_1 FOREIGN KEY (itemid) REFERENCES items (item_id) ON DELETE CASCADE ON UPDATE CASCADE,
  CONSTRAINT reviews_ibfk_2 FOREIGN KEY (username) REFERENCES usercreate (user_email) ON DELETE CASCADE ON UPDATE CASCADE
);
